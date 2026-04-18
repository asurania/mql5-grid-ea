"""Historical backtest for the session-aware Forex grid policy.

Assumptions and simplifications:
- The simulator operates on minute OHLC bars and is deterministic. It does not
  attempt to reconstruct intrabar tick order.
- Initial basket legs are opened at the first bar open for the session.
- Expansion checks use the bar low/high against the most recent leg per side.
  Multiple legs may be added inside one bar if price moved across several grid
  steps.
- Directional basket TP/SL is evaluated against the dominant exposure side's
  weighted-average entry price. Near net-flat hedged baskets can instead use a
  currency TP threshold when configured.
- Force-close events execute at the first available bar open at or after the
  session cutoff. If no later bar exists, the basket is closed on the final bar
  close for that session.

The goal is a production-usable historical harness for comparing grid policies,
not a tick-accurate execution engine.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Literal
from zoneinfo import ZoneInfo

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from massive_pipeline.trading_config import load_config


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "trading_config.json"
DEFAULT_GRID_POLICY = ROOT / "data" / "live" / "policy" / "grid_policy.json"
PRICE_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "backtest" / "grid_policy"
NY_TZ = ZoneInfo("America/New_York")
UTC = timezone.utc

SIDE_BUY = "buy"
SIDE_SELL = "sell"
SessionName = Literal["asia", "london", "new_york"]
SESSION_ALL = "all"
NEAR_FLAT_LOT_RATIO = 0.10


@dataclass(frozen=True)
class Policy:
    pair: str
    policy_id: str
    grid_mode: str
    seed_mode: str
    step_pips: float
    initial_lot: float
    multiplier: float
    max_trades_per_side: int
    max_gross_lots: float
    basket_tp_pips: float
    basket_sl_pips: float
    basket_tp_currency: float | None
    max_basket_drawdown_currency: float | None
    allow_new_basket: bool
    risk_mode: str
    account_equity: float
    source: str


@dataclass(frozen=True)
class SessionSpec:
    pair: str
    session_name: SessionName
    session_start_utc: datetime
    session_end_utc: datetime
    daily_liquidation_utc: datetime | None
    policy: Policy


@dataclass(frozen=True)
class Leg:
    side: str
    entry_price: float
    lot: float


@dataclass
class Basket:
    legs: list[Leg] = field(default_factory=list)
    total_legs_opened: int = 0
    realized_pnl: float = 0.0
    max_open_legs: int = 0
    max_gross_lots: float = 0.0
    max_adverse_excursion: float = 0.0
    max_drawdown: float = 0.0
    _peak_equity: float = 0.0

    def add_leg(self, leg: Leg) -> None:
        self.legs.append(leg)
        self.total_legs_opened += 1
        self.max_open_legs = max(self.max_open_legs, len(self.legs))
        self.max_gross_lots = max(self.max_gross_lots, self.gross_lots)

    @property
    def trade_count(self) -> int:
        return self.total_legs_opened

    @property
    def gross_lots(self) -> float:
        return round(sum(leg.lot for leg in self.legs), 6)

    def side_legs(self, side: str) -> list[Leg]:
        return [leg for leg in self.legs if leg.side == side]

    def side_lots(self, side: str) -> float:
        return sum(leg.lot for leg in self.legs if leg.side == side)

    def side_count(self, side: str) -> int:
        return sum(1 for leg in self.legs if leg.side == side)

    def last_leg(self, side: str) -> Leg | None:
        for leg in reversed(self.legs):
            if leg.side == side:
                return leg
        return None

    def weighted_avg_entry(self, side: str) -> float | None:
        side_legs = self.side_legs(side)
        total_lot = sum(leg.lot for leg in side_legs)
        if total_lot <= 0:
            return None
        return sum(leg.entry_price * leg.lot for leg in side_legs) / total_lot

    def net_lots(self) -> float:
        return self.side_lots(SIDE_BUY) - self.side_lots(SIDE_SELL)

    def dominant_side(self) -> str | None:
        buy_lots = self.side_lots(SIDE_BUY)
        sell_lots = self.side_lots(SIDE_SELL)
        if buy_lots > sell_lots:
            return SIDE_BUY
        if sell_lots > buy_lots:
            return SIDE_SELL
        if buy_lots > 0:
            return SIDE_BUY
        return None

    def is_near_flat(self) -> bool:
        gross = self.gross_lots
        if gross <= 0:
            return False
        return abs(self.net_lots()) / gross <= NEAR_FLAT_LOT_RATIO

    def pnl_at(self, price: float, pip_size: float, pip_value_per_001_lot: float) -> float:
        pnl = 0.0
        for leg in self.legs:
            diff = price - leg.entry_price if leg.side == SIDE_BUY else leg.entry_price - price
            pnl += (diff / pip_size) * pip_value_per_001_lot * (leg.lot / 0.01)
        return pnl

    def update_drawdown(self, floating_pnl: float) -> None:
        equity = self.realized_pnl + floating_pnl
        self._peak_equity = max(self._peak_equity, equity)
        self.max_drawdown = max(self.max_drawdown, self._peak_equity - equity)
        self.max_adverse_excursion = max(self.max_adverse_excursion, max(0.0, -floating_pnl))

    def close(self, price: float, pip_size: float, pip_value_per_001_lot: float) -> float:
        pnl = self.pnl_at(price, pip_size, pip_value_per_001_lot)
        self.realized_pnl += pnl
        self.legs.clear()
        return pnl


@dataclass(frozen=True)
class SimulationResult:
    pair: str
    session_name: str
    session_start_utc: datetime
    session_end_utc: datetime
    policy_id: str
    policy_source: str
    risk_mode: str
    account_equity: float
    trade_count: int
    gross_lots: float
    realized_pnl: float
    max_drawdown: float
    max_adverse_excursion: float
    max_open_legs: int
    exit_reason: str
    bars_processed: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest the historical Forex grid policy on minute bars.")
    parser.add_argument("--pair", action="append", required=True, help="Pair to backtest. Repeat for multiple pairs.")
    parser.add_argument("--start-date", type=parse_date, help="Inclusive start date in YYYY-MM-DD.")
    parser.add_argument("--end-date", type=parse_date, help="Inclusive end date in YYYY-MM-DD.")
    parser.add_argument("--session", choices=["asia", "london", "new_york", "all"], default="all")
    parser.add_argument("--grid-policy", type=Path, default=DEFAULT_GRID_POLICY)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--policy-id", help="Template policy id from config.grid_templates.")
    parser.add_argument("--risk-mode", help="Override account risk mode.")
    parser.add_argument("--account-equity", type=float, help="Override account equity.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-sessions", type=int, help="Limit number of simulated sessions for smoke tests.")
    parser.add_argument("--use-live-policy", dest="use_live_policy", action="store_true", help="Prefer pair-specific policies from the live policy file.")
    parser.add_argument("--no-use-live-policy", dest="use_live_policy", action="store_false", help="Ignore the live policy file and use config templates only.")
    parser.set_defaults(use_live_policy=True)
    return parser.parse_args()


def parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_pairs(raw_pairs: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for pair in raw_pairs:
        normalized = pair.upper()
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def resolve_account_settings(config: dict[str, Any], risk_mode: str | None, account_equity: float | None) -> tuple[str, float]:
    account = config.get("account", {})
    resolved_risk_mode = risk_mode or account.get("risk_mode", "medium")
    resolved_equity = float(account_equity if account_equity is not None else account.get("equity", 10000.0))
    return resolved_risk_mode, resolved_equity


def build_policy(
    *,
    pair: str,
    session_name: str,
    session_cfg: dict[str, Any],
    config: dict[str, Any],
    live_pair_policies: dict[str, dict[str, Any]],
    policy_id_override: str | None,
    risk_mode: str,
    account_equity: float,
    use_live_policy: bool,
) -> Policy:
    templates = config.get("grid_templates", {})
    if policy_id_override:
        if policy_id_override not in templates:
            raise KeyError(f"Unknown policy-id '{policy_id_override}' in config.grid_templates")
        base = dict(templates[policy_id_override])
        resolved_policy_id = policy_id_override
        source = "config_template_override"
    elif use_live_policy and pair in live_pair_policies:
        base = dict(live_pair_policies[pair])
        resolved_policy_id = str(base.get("policy_id") or f"live_{pair.lower()}")
        source = "live_policy"
    else:
        fallback_id = choose_default_template_id(templates)
        base = dict(templates[fallback_id])
        resolved_policy_id = fallback_id
        source = "config_template_default"

    basket_tp_pips = float(base.get("basket_tp_pips", session_cfg.get("tp_pips", 3.0)))
    basket_sl_pips = float(base.get("basket_sl_pips", session_cfg.get("sl_pips", 50.0)))

    return Policy(
        pair=pair,
        policy_id=resolved_policy_id,
        grid_mode=str(base.get("grid_mode", "both_sides")),
        seed_mode=str(base.get("seed_mode", "both_sides")),
        step_pips=float(base.get("step_pips", 0.0)),
        initial_lot=float(base.get("initial_lot", 0.0)),
        multiplier=float(base.get("multiplier", 1.0)),
        max_trades_per_side=int(base.get("max_trades_per_side", 0)),
        max_gross_lots=float(base.get("max_gross_lots", 0.0)),
        basket_tp_pips=basket_tp_pips,
        basket_sl_pips=basket_sl_pips,
        basket_tp_currency=optional_positive_float(base.get("basket_tp_currency")),
        max_basket_drawdown_currency=optional_positive_float(base.get("max_basket_drawdown_currency")),
        allow_new_basket=bool(base.get("allow_new_basket", True)),
        risk_mode=risk_mode,
        account_equity=account_equity,
        source=source,
    )


def choose_default_template_id(templates: dict[str, dict[str, Any]]) -> str:
    for candidate in ("both_sides_normal", "classic_consolidation_normal", "both_sides_conservative"):
        if candidate in templates:
            return candidate
    for name, payload in templates.items():
        if payload.get("allow_new_basket", True):
            return name
    if not templates:
        raise ValueError("No grid templates found in config.")
    return next(iter(templates))


def optional_positive_float(value: Any) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return parsed if parsed > 0 else None


def build_session_specs(
    *,
    pairs: list[str],
    config: dict[str, Any],
    live_pair_policies: dict[str, dict[str, Any]],
    session_filter: str,
    start_date: date,
    end_date: date,
    policy_id_override: str | None,
    risk_mode: str,
    account_equity: float,
    use_live_policy: bool,
) -> list[SessionSpec]:
    sessions_cfg: dict[str, dict[str, Any]] = config.get("sessions", {})
    daily_liq = tuple(config.get("daily_liquidation_utc", [20, 50]))
    selected_sessions: list[str]
    if session_filter == SESSION_ALL:
        selected_sessions = [name for name, payload in sessions_cfg.items() if payload.get("enabled", True)]
    else:
        selected_sessions = [session_filter]

    specs: list[SessionSpec] = []
    current = start_date
    while current <= end_date:
        for pair in pairs:
            for session_name in selected_sessions:
                session_cfg = sessions_cfg.get(session_name)
                if not session_cfg or not session_cfg.get("enabled", True):
                    continue
                start_utc, end_utc = session_bounds_for_date(current, session_cfg)
                daily_liq_utc = daily_liquidation_within_window(start_utc, end_utc, daily_liq)
                specs.append(
                    SessionSpec(
                        pair=pair,
                        session_name=session_name,  # type: ignore[arg-type]
                        session_start_utc=start_utc,
                        session_end_utc=end_utc,
                        daily_liquidation_utc=daily_liq_utc,
                        policy=build_policy(
                            pair=pair,
                            session_name=session_name,
                            session_cfg=session_cfg,
                            config=config,
                            live_pair_policies=live_pair_policies,
                            policy_id_override=policy_id_override,
                            risk_mode=risk_mode,
                            account_equity=account_equity,
                            use_live_policy=use_live_policy,
                        ),
                    )
                )
        current += timedelta(days=1)
    specs.sort(key=lambda spec: (spec.session_start_utc, spec.pair, spec.session_name))
    return specs


def session_bounds_for_date(anchor_date: date, session_cfg: dict[str, Any]) -> tuple[datetime, datetime]:
    start_hour, start_minute = session_cfg["start_ny_time"]
    close_hour_utc, close_minute_utc = session_cfg["close_utc"]
    local_start = datetime.combine(anchor_date, time(start_hour, start_minute), tzinfo=NY_TZ)
    start_utc = local_start.astimezone(UTC)
    end_utc = datetime.combine(start_utc.date(), time(close_hour_utc, close_minute_utc), tzinfo=UTC)
    if end_utc <= start_utc:
        end_utc += timedelta(days=1)
    return start_utc, end_utc


def daily_liquidation_within_window(start_utc: datetime, end_utc: datetime, daily_liq_hm: tuple[int, int]) -> datetime | None:
    hour, minute = daily_liq_hm
    candidates = [
        datetime.combine(start_utc.date(), time(hour, minute), tzinfo=UTC),
        datetime.combine(end_utc.date(), time(hour, minute), tzinfo=UTC),
    ]
    valid = [candidate for candidate in candidates if start_utc <= candidate <= end_utc]
    return min(valid) if valid else None


def determine_date_bounds(
    start_date: date | None,
    end_date: date | None,
    price_root: Path,
) -> tuple[date, date]:
    if start_date and end_date:
        if end_date < start_date:
            raise ValueError("--end-date must be on or after --start-date")
        return start_date, end_date

    available = sorted(price_root.glob("year=*/month=*/data.parquet"))
    if not available:
        raise FileNotFoundError(f"No parquet data found under {price_root}")

    first_parts = available[0].parts
    last_parts = available[-1].parts
    first_year, first_month = int(first_parts[-3].split("=")[1]), int(first_parts[-2].split("=")[1])
    last_year, last_month = int(last_parts[-3].split("=")[1]), int(last_parts[-2].split("=")[1])
    inferred_start = date(first_year, first_month, 1)
    inferred_end = (date(last_year, last_month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return start_date or inferred_start, end_date or inferred_end


def month_partition_paths(price_root: Path, start_dt: datetime, end_dt: datetime) -> list[Path]:
    current = date(start_dt.year, start_dt.month, 1)
    final = date(end_dt.year, end_dt.month, 1)
    paths: list[Path] = []
    while current <= final:
        path = price_root / f"year={current.year:04d}" / f"month={current.month:02d}" / "data.parquet"
        if path.exists():
            paths.append(path)
        current = (current + timedelta(days=32)).replace(day=1)
    return paths


def load_live_pair_policies(grid_policy_path: Path) -> dict[str, dict[str, Any]]:
    if not grid_policy_path.exists():
        return {}
    payload = load_json(grid_policy_path)
    rows = payload.get("pairs", [])
    return {str(row["pair"]).upper(): row for row in rows if row.get("pair")}


def load_bars(
    *,
    price_root: Path,
    pairs: list[str],
    session_specs: list[SessionSpec],
) -> pl.DataFrame:
    if not session_specs:
        return pl.DataFrame(
            schema={
                "pair": pl.String,
                "timestamp_utc": pl.Datetime(time_zone="UTC"),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
            }
        )

    min_ts = min(spec.session_start_utc for spec in session_specs)
    max_ts = max(spec.session_end_utc for spec in session_specs)
    paths = month_partition_paths(price_root, min_ts, max_ts)
    if not paths:
        raise FileNotFoundError(f"No parquet partitions found for {min_ts.date()} to {max_ts.date()} under {price_root}")

    scan = (
        pl.scan_parquet([str(path) for path in paths])
        .filter(
            pl.col("pair").is_in(pairs)
            & (pl.col("timestamp_utc") >= pl.lit(min_ts))
            & (pl.col("timestamp_utc") <= pl.lit(max_ts))
        )
        .select(["pair", "timestamp_utc", "open", "high", "low", "close"])
        .sort(["pair", "timestamp_utc"])
    )
    return scan.collect()


def seed_sides(policy: Policy) -> list[str]:
    if policy.grid_mode == "buy_only":
        return [SIDE_BUY]
    if policy.grid_mode == "sell_only":
        return [SIDE_SELL]
    if policy.grid_mode == "both_sides" and policy.seed_mode == "both_sides":
        return [SIDE_BUY, SIDE_SELL]
    if policy.grid_mode == "both_sides" and policy.seed_mode == "single_side":
        return [SIDE_BUY]
    raise ValueError(f"Unsupported grid/seed mode combination: {policy.grid_mode}/{policy.seed_mode}")


def expansion_sides(policy: Policy) -> list[str]:
    return seed_sides(policy)


def next_lot(policy: Policy, current_count: int) -> float:
    return round(policy.initial_lot * (policy.multiplier ** current_count), 6)


def can_add_leg(basket: Basket, policy: Policy, side: str) -> bool:
    if basket.side_count(side) >= policy.max_trades_per_side:
        return False
    candidate_lot = next_lot(policy, basket.side_count(side))
    return basket.gross_lots + candidate_lot <= policy.max_gross_lots + 1e-12


def maybe_expand_side(
    *,
    basket: Basket,
    policy: Policy,
    side: str,
    low_price: float,
    high_price: float,
    pip_size: float,
) -> None:
    if policy.step_pips <= 0:
        return
    step_price = policy.step_pips * pip_size
    while can_add_leg(basket, policy, side):
        last_leg = basket.last_leg(side)
        if last_leg is None:
            return
        trigger_price = last_leg.entry_price - step_price if side == SIDE_BUY else last_leg.entry_price + step_price
        breached = low_price <= trigger_price if side == SIDE_BUY else high_price >= trigger_price
        if not breached:
            return
        basket.add_leg(Leg(side=side, entry_price=trigger_price, lot=next_lot(policy, basket.side_count(side))))


def floating_extremes(basket: Basket, low: float, high: float, close: float, pip_size: float, pip_value_per_001_lot: float) -> tuple[float, float]:
    values = [
        basket.pnl_at(low, pip_size, pip_value_per_001_lot),
        basket.pnl_at(high, pip_size, pip_value_per_001_lot),
        basket.pnl_at(close, pip_size, pip_value_per_001_lot),
    ]
    return min(values), max(values)


def evaluate_exit(
    *,
    basket: Basket,
    policy: Policy,
    bar_open: float,
    bar_high: float,
    bar_low: float,
    pip_size: float,
    pip_value_per_001_lot: float,
) -> tuple[str, float] | None:
    if not basket.legs:
        return None

    if policy.max_basket_drawdown_currency is not None:
        floating_min, _ = floating_extremes(basket, bar_low, bar_high, bar_open, pip_size, pip_value_per_001_lot)
        if -floating_min >= policy.max_basket_drawdown_currency:
            return "drawdown_limit", bar_open

    if basket.is_near_flat() and policy.basket_tp_currency is not None:
        _, floating_max = floating_extremes(basket, bar_low, bar_high, bar_open, pip_size, pip_value_per_001_lot)
        if floating_max >= policy.basket_tp_currency:
            return "basket_tp_currency", bar_open
        return None

    dominant_side = basket.dominant_side()
    if dominant_side is None:
        return None

    avg_entry = basket.weighted_avg_entry(dominant_side)
    if avg_entry is None:
        return None

    tp_distance = policy.basket_tp_pips * pip_size
    sl_distance = policy.basket_sl_pips * pip_size

    if dominant_side == SIDE_BUY:
        sl_price = avg_entry - sl_distance
        tp_price = avg_entry + tp_distance
        if bar_low <= sl_price:
            return "basket_sl_pips", sl_price
        if bar_high >= tp_price:
            return "basket_tp_pips", tp_price
    else:
        sl_price = avg_entry + sl_distance
        tp_price = avg_entry - tp_distance
        if bar_high >= sl_price:
            return "basket_sl_pips", sl_price
        if bar_low <= tp_price:
            return "basket_tp_pips", tp_price
    return None


def simulate_session(
    spec: SessionSpec,
    session_bars: pl.DataFrame,
    pip_size: float,
    pip_value_per_001_lot: float,
) -> SimulationResult:
    basket = Basket()
    policy = spec.policy

    if not policy.allow_new_basket or policy.initial_lot <= 0 or policy.max_trades_per_side <= 0 or policy.max_gross_lots <= 0:
        return SimulationResult(
            pair=spec.pair,
            session_name=spec.session_name,
            session_start_utc=spec.session_start_utc,
            session_end_utc=spec.session_end_utc,
            policy_id=policy.policy_id,
            policy_source=policy.source,
            risk_mode=policy.risk_mode,
            account_equity=policy.account_equity,
            trade_count=0,
            gross_lots=0.0,
            realized_pnl=0.0,
            max_drawdown=0.0,
            max_adverse_excursion=0.0,
            max_open_legs=0,
            exit_reason="policy_disabled",
            bars_processed=0,
        )

    if session_bars.height == 0:
        return SimulationResult(
            pair=spec.pair,
            session_name=spec.session_name,
            session_start_utc=spec.session_start_utc,
            session_end_utc=spec.session_end_utc,
            policy_id=policy.policy_id,
            policy_source=policy.source,
            risk_mode=policy.risk_mode,
            account_equity=policy.account_equity,
            trade_count=0,
            gross_lots=0.0,
            realized_pnl=0.0,
            max_drawdown=0.0,
            max_adverse_excursion=0.0,
            max_open_legs=0,
            exit_reason="no_bars",
            bars_processed=0,
        )

    rows = session_bars.iter_rows(named=True)
    first_row = next(rows)
    entry_price = float(first_row["open"])
    for side in seed_sides(policy):
        basket.add_leg(Leg(side=side, entry_price=entry_price, lot=policy.initial_lot))

    last_close = float(first_row["close"])
    bars_processed = 1
    exit_reason = "session_close"

    first_floating_min, _ = floating_extremes(basket, float(first_row["low"]), float(first_row["high"]), last_close, pip_size, pip_value_per_001_lot)
    basket.update_drawdown(first_floating_min)

    cutoff_reason, cutoff_ts = active_cutoff(spec)
    if cutoff_ts is not None and spec.session_start_utc >= cutoff_ts:
        basket.close(entry_price, pip_size, pip_value_per_001_lot)
        exit_reason = cutoff_reason
        return build_result(spec, basket, exit_reason, bars_processed)

    for row in rows:
        ts = row["timestamp_utc"]
        bar_open = float(row["open"])
        bar_high = float(row["high"])
        bar_low = float(row["low"])
        bar_close = float(row["close"])
        bars_processed += 1

        if cutoff_ts is not None and ts >= cutoff_ts:
            basket.close(bar_open, pip_size, pip_value_per_001_lot)
            exit_reason = cutoff_reason
            return build_result(spec, basket, exit_reason, bars_processed)

        for side in expansion_sides(policy):
            maybe_expand_side(
                basket=basket,
                policy=policy,
                side=side,
                low_price=bar_low,
                high_price=bar_high,
                pip_size=pip_size,
            )

        exit_hit = evaluate_exit(
            basket=basket,
            policy=policy,
            bar_open=bar_open,
            bar_high=bar_high,
            bar_low=bar_low,
            pip_size=pip_size,
            pip_value_per_001_lot=pip_value_per_001_lot,
        )
        if exit_hit is not None:
            exit_reason, exit_price = exit_hit
            basket.close(exit_price, pip_size, pip_value_per_001_lot)
            return build_result(spec, basket, exit_reason, bars_processed)

        floating_min, _ = floating_extremes(basket, bar_low, bar_high, bar_close, pip_size, pip_value_per_001_lot)
        basket.update_drawdown(floating_min)
        last_close = bar_close

    basket.close(last_close, pip_size, pip_value_per_001_lot)
    return build_result(spec, basket, exit_reason, bars_processed)


def active_cutoff(spec: SessionSpec) -> tuple[str, datetime | None]:
    if spec.daily_liquidation_utc is not None and spec.daily_liquidation_utc <= spec.session_end_utc:
        return "daily_liquidation", spec.daily_liquidation_utc
    return "session_close", spec.session_end_utc


def build_result(spec: SessionSpec, basket: Basket, exit_reason: str, bars_processed: int) -> SimulationResult:
    return SimulationResult(
        pair=spec.pair,
        session_name=spec.session_name,
        session_start_utc=spec.session_start_utc,
        session_end_utc=spec.session_end_utc,
        policy_id=spec.policy.policy_id,
        policy_source=spec.policy.source,
        risk_mode=spec.policy.risk_mode,
        account_equity=spec.policy.account_equity,
        trade_count=basket.trade_count,
        gross_lots=round(basket.max_gross_lots, 6),
        realized_pnl=round(basket.realized_pnl, 6),
        max_drawdown=round(basket.max_drawdown, 6),
        max_adverse_excursion=round(basket.max_adverse_excursion, 6),
        max_open_legs=basket.max_open_legs,
        exit_reason=exit_reason,
        bars_processed=bars_processed,
    )


def results_to_frame(results: list[SimulationResult]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "pair": row.pair,
                "session_name": row.session_name,
                "session_start_utc": row.session_start_utc,
                "session_end_utc": row.session_end_utc,
                "policy_id": row.policy_id,
                "policy_source": row.policy_source,
                "risk_mode": row.risk_mode,
                "account_equity": row.account_equity,
                "trade_count": row.trade_count,
                "gross_lots": row.gross_lots,
                "realized_pnl": row.realized_pnl,
                "max_drawdown": row.max_drawdown,
                "max_adverse_excursion": row.max_adverse_excursion,
                "max_open_legs": row.max_open_legs,
                "exit_reason": row.exit_reason,
                "bars_processed": row.bars_processed,
            }
            for row in results
        ]
    )


def summarize_results(results_df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, Any]]:
    if results_df.height == 0:
        empty_pair = pl.DataFrame(
            schema={
                "pair": pl.String,
                "sessions": pl.Int64,
                "winning_sessions": pl.Int64,
                "win_rate": pl.Float64,
                "total_pnl": pl.Float64,
                "avg_pnl": pl.Float64,
                "median_pnl": pl.Float64,
                "worst_drawdown": pl.Float64,
                "avg_trade_count": pl.Float64,
            }
        )
        empty_policy = empty_pair.rename({"pair": "policy_id"})
        return empty_pair, empty_policy, {"sessions": 0, "total_pnl": 0.0}

    with_win = results_df.with_columns((pl.col("realized_pnl") > 0).cast(pl.Int64).alias("is_win"))
    summary_by_pair = (
        with_win.group_by("pair")
        .agg(
            [
                pl.len().alias("sessions"),
                pl.col("is_win").sum().alias("winning_sessions"),
                pl.col("realized_pnl").sum().alias("total_pnl"),
                pl.col("realized_pnl").mean().alias("avg_pnl"),
                pl.col("realized_pnl").median().alias("median_pnl"),
                pl.col("max_drawdown").max().alias("worst_drawdown"),
                pl.col("trade_count").mean().alias("avg_trade_count"),
            ]
        )
        .with_columns((pl.col("winning_sessions") / pl.col("sessions")).alias("win_rate"))
        .sort("pair")
    )
    summary_by_policy = (
        with_win.group_by("policy_id")
        .agg(
            [
                pl.len().alias("sessions"),
                pl.col("is_win").sum().alias("winning_sessions"),
                pl.col("realized_pnl").sum().alias("total_pnl"),
                pl.col("realized_pnl").mean().alias("avg_pnl"),
                pl.col("realized_pnl").median().alias("median_pnl"),
                pl.col("max_drawdown").max().alias("worst_drawdown"),
                pl.col("trade_count").mean().alias("avg_trade_count"),
            ]
        )
        .with_columns((pl.col("winning_sessions") / pl.col("sessions")).alias("win_rate"))
        .sort("policy_id")
    )

    overall = {
        "sessions": int(results_df.height),
        "pairs": sorted(results_df["pair"].unique().to_list()),
        "policies": sorted(results_df["policy_id"].unique().to_list()),
        "total_pnl": float(results_df["realized_pnl"].sum()),
        "avg_pnl": float(results_df["realized_pnl"].mean()),
        "median_pnl": float(results_df["realized_pnl"].median()),
        "best_session_pnl": float(results_df["realized_pnl"].max()),
        "worst_session_pnl": float(results_df["realized_pnl"].min()),
        "worst_drawdown": float(results_df["max_drawdown"].max()),
        "avg_trade_count": float(results_df["trade_count"].mean()),
        "avg_gross_lots": float(results_df["gross_lots"].mean()),
        "winning_sessions": int((results_df["realized_pnl"] > 0).sum()),
        "non_positive_sessions": int((results_df["realized_pnl"] <= 0).sum()),
        "exit_reason_counts": group_count_dict(results_df["exit_reason"].to_list()),
    }
    return summary_by_pair, summary_by_policy, overall


def group_count_dict(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def bars_for_spec(bars_df: pl.DataFrame, spec: SessionSpec) -> pl.DataFrame:
    return bars_df.filter(
        (pl.col("pair") == spec.pair)
        & (pl.col("timestamp_utc") >= pl.lit(spec.session_start_utc))
        & (pl.col("timestamp_utc") < pl.lit(spec.session_end_utc))
    )


def main() -> None:
    args = parse_args()
    config = load_json(args.config) if args.config != DEFAULT_CONFIG else load_config()
    pairs = normalize_pairs(args.pair)
    risk_mode, account_equity = resolve_account_settings(config, args.risk_mode, args.account_equity)
    start_date, end_date = determine_date_bounds(args.start_date, args.end_date, PRICE_DIR)
    live_pair_policies = load_live_pair_policies(args.grid_policy) if args.use_live_policy else {}

    session_specs = build_session_specs(
        pairs=pairs,
        config=config,
        live_pair_policies=live_pair_policies,
        session_filter=args.session,
        start_date=start_date,
        end_date=end_date,
        policy_id_override=args.policy_id,
        risk_mode=risk_mode,
        account_equity=account_equity,
        use_live_policy=args.use_live_policy,
    )
    if args.max_sessions is not None:
        session_specs = session_specs[: args.max_sessions]

    bars_df = load_bars(price_root=PRICE_DIR, pairs=pairs, session_specs=session_specs)
    pip_cfg = config.get("pip_config", {})
    pip_size_map: dict[str, float] = pip_cfg.get("pip_size", {})
    pip_value_map: dict[str, float] = pip_cfg.get("pip_value_per_001_lot", {})

    results: list[SimulationResult] = []
    for spec in session_specs:
        pip_size = float(pip_size_map[spec.pair])
        pip_value_per_001_lot = float(pip_value_map[spec.pair])
        results.append(
            simulate_session(
                spec=spec,
                session_bars=bars_for_spec(bars_df, spec),
                pip_size=pip_size,
                pip_value_per_001_lot=pip_value_per_001_lot,
            )
        )

    results_df = results_to_frame(results)
    summary_by_pair, summary_by_policy, overall = summarize_results(results_df)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results_df.write_csv(args.output_dir / "session_results.csv")
    results_df.write_parquet(args.output_dir / "session_results.parquet")
    summary_by_pair.write_csv(args.output_dir / "summary_by_pair.csv")
    summary_by_policy.write_csv(args.output_dir / "summary_by_policy.csv")

    metadata = {
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "pairs": pairs,
        "session_filter": args.session,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "use_live_policy": args.use_live_policy,
        "policy_id_override": args.policy_id,
        "risk_mode": risk_mode,
        "account_equity": account_equity,
        "max_sessions": args.max_sessions,
        "live_policy_path": str(args.grid_policy),
        "config_path": str(args.config),
        "overall": overall,
    }
    (args.output_dir / "overall_summary.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(json.dumps(metadata, indent=2))
    print(summary_by_pair)
    print(summary_by_policy)


if __name__ == "__main__":
    main()
