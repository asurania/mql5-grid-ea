from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from massive_pipeline.legacy_grid_parity import (
    GridPolicy,
    LegacyGridParityEngine,
    MarketSnapshot,
    NormalizedRiskLimits,
    SessionFilterConfig,
    TimeWindowConfig,
    VariableEAConfig,
    compute_gann_hilo,
    compute_sma,
    session_filter_allows,
)
from massive_pipeline.trading_config import load_config

ROOT = Path(__file__).resolve().parents[2]
PRICE_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
POLICY_FILE = ROOT / "config" / "pair_session_policy.json"
OUT_FILE = ROOT / "data" / "backtest" / "legacy_parity" / "pair_session_backtest_summary.json"
TARGET_PAIRS = ["AUDNZD", "AUDUSD", "GBPJPY", "GBPUSD", "USDJPY", "NZDUSD", "AUDJPY"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest pair-session policy config")
    parser.add_argument("--pair", action="append")
    parser.add_argument("--max-rows", type=int, default=120000)
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_price_frame(pair: str, max_rows: int) -> pl.DataFrame:
    paths = sorted(PRICE_DIR.glob('year=*/month=*/data.parquet'))
    return (
        pl.scan_parquet([str(p) for p in paths])
        .filter(pl.col("pair") == pair.upper())
        .select(["timestamp_utc", "open", "high", "low", "close"])
        .sort("timestamp_utc")
        .head(max_rows)
        .collect()
    )


def to_windows(items: list[dict]) -> tuple[TimeWindowConfig, ...]:
    return tuple(TimeWindowConfig(x["start"], x["end"], float(x["value"])) for x in items)


def resolve_initial_lot(session_cfg: dict, config: dict, lot_sizing: dict | None = None) -> float:
    initial_lot = float(session_cfg.get("initial_lot", 0.01))
    mode = session_cfg.get("initial_lot_mode") or (lot_sizing or {}).get("mode")
    if mode != "equity_scaled":
        return initial_lot
    equity = float(config["account"]["equity"])
    base_equity = float(session_cfg.get("base_equity") or (lot_sizing or {}).get("base_equity") or 10000.0)
    lot_step = float((lot_sizing or {}).get("lot_step", 0.01))
    min_lot = float((lot_sizing or {}).get("min_lot", 0.01))
    max_lot = float((lot_sizing or {}).get("max_lot", 5.0))
    scaled = initial_lot * (equity / base_equity)
    rounded = round(scaled / lot_step) * lot_step
    return max(min_lot, min(max_lot, round(rounded, 4)))


def build_policy(session_cfg: dict, config: dict | None = None, lot_sizing: dict | None = None) -> GridPolicy:
    step_mode = session_cfg.get("step_mode", "fixed")
    step_pips = float(session_cfg.get("step_pips", 10.0))
    fixed_step = step_pips
    variable_steps = (step_pips,) if step_mode == "fixed" else tuple(float(x["value"]) for x in session_cfg.get("variable_step_schedule", [])) or (step_pips,)
    resolved_initial_lot = resolve_initial_lot(session_cfg, config or {"account": {"equity": 10000.0}}, lot_sizing)
    return GridPolicy(
        step_mode="fixed" if step_mode == "fixed" else "variable",
        fixed_step_pips=fixed_step,
        variable_steps_pips=variable_steps,
        multiplier=float(session_cfg.get("multiplier", 1.1)),
        initial_lot=resolved_initial_lot,
        max_lot=5.0,
        max_levels_buy=int(session_cfg.get("grid_levels", 6)),
        max_levels_sell=int(session_cfg.get("grid_levels", 6)),
        tp_pips_buy=float(session_cfg.get("tp_pips", 4.0)),
        tp_pips_sell=float(session_cfg.get("tp_pips", 4.0)),
        sl_pips=float(session_cfg.get("sl_pips", 50.0)),
        variable_ea=VariableEAConfig(
            enabled=bool(session_cfg.get("variable_step_schedule") or session_cfg.get("variable_tp_schedule")),
            mode="managed",
            step_windows=to_windows(session_cfg.get("variable_step_schedule", [])),
            tp_windows=to_windows(session_cfg.get("variable_tp_schedule", [])),
        ),
    )


def build_risk(config: dict, session_cfg: dict) -> NormalizedRiskLimits:
    equity = float(config["account"]["equity"])
    risk_mode = config["account"]["risk_mode"]
    account_dd = equity * float(config["risk"]["budget_pct"][risk_mode])
    return NormalizedRiskLimits(
        account_equity=equity,
        max_account_drawdown_currency=round(account_dd, 2),
        max_basket_drawdown_currency=float(session_cfg.get("drawdown_limit_currency", 150.0)),
        target_basket_profit_currency=round(equity * float(config["risk"]["target_profit_pct"][risk_mode]), 2),
    )


def build_session_filter(policy_root: dict, session_name: str) -> SessionFilterConfig:
    session = policy_root["sessions"][session_name]
    return SessionFilterConfig(
        start_hhmm=session["start"],
        stop_hhmm=session["end"],
        managed_close_minutes=30,
        timezone_name=policy_root.get("timezone", "America/Edmonton"),
        allowed_weekdays=(0, 1, 2, 3, 4),
        exempted_month_days=(3, 6, 8, 27),
    )


def segmented_rows(frame: pl.DataFrame, session_filter: SessionFilterConfig) -> list[list[dict]]:
    segments: list[list[dict]] = []
    current: list[dict] = []
    for row in frame.iter_rows(named=True):
        ts = row["timestamp_utc"]
        ts_utc = ts if isinstance(ts, datetime) and ts.tzinfo else datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if session_filter_allows(ts_utc, session_filter):
            row = dict(row)
            row["timestamp_utc"] = ts_utc
            current.append(row)
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def run_segment(segment: list[dict], policy: GridPolicy, risk: NormalizedRiskLimits, pip_size: float, pip_value: float, managed_close_minutes: int) -> dict:
    closes = [float(r["close"]) for r in segment]
    highs = [float(r["high"]) for r in segment]
    lows = [float(r["low"]) for r in segment]
    ma = compute_sma(closes, 21)
    gann = compute_gann_hilo(highs, lows, closes, 21)
    engine = LegacyGridParityEngine(policy, risk, pip_size, pip_value)
    session_end = segment[-1]["timestamp_utc"]
    managed_cut = session_end.timestamp() - managed_close_minutes * 60
    for idx, row in enumerate(segment):
        if ma[idx] is None:
            continue
        ts_utc = row["timestamp_utc"]
        snapshot = MarketSnapshot(
            timestamp_utc=ts_utc,
            bid=float(row["close"]),
            ask=float(row["close"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            ma_value=float(ma[idx]),
            gann_value=float(gann[idx]) if gann[idx] is not None else None,
        )
        engine.process_snapshot(snapshot, managed_closing=ts_utc.timestamp() >= managed_cut)
    final_close = float(segment[-1]["close"])
    final_snapshot = MarketSnapshot(
        timestamp_utc=session_end,
        bid=final_close,
        ask=final_close,
        high=final_close,
        low=final_close,
        close=final_close,
        ma_value=float(ma[-1]) if ma[-1] is not None else final_close,
        gann_value=float(gann[-1]) if gann[-1] is not None else None,
    )
    engine.process_snapshot(final_snapshot, force_flatten=True)
    return {
        "rows": len(segment),
        "buy_realized_pnl": engine.state.buy_basket.realized_pnl_currency,
        "sell_realized_pnl": engine.state.sell_basket.realized_pnl_currency,
        "buy_closed_reason": engine.state.buy_basket.closed_reason,
        "sell_closed_reason": engine.state.sell_basket.closed_reason,
        "breach_reason": engine.state.breach_reason,
    }


def run_pair(pair: str, config: dict, policy_root: dict, max_rows: int) -> dict:
    frame = load_price_frame(pair, max_rows)
    if frame.height == 0:
        return {"pair": pair, "missing_data": True}
    pair_policy = policy_root["pairs"].get(pair, {})
    pip_size_map = config["pip_config"]["pip_size"]
    pip_value_map = config["pip_config"]["pip_value_per_001_lot"]
    pip_size = float(pip_size_map.get(pair, 0.01 if pair.endswith("JPY") else 0.0001))
    pip_value = float(pip_value_map.get(pair, pip_value_map.get("GBPUSD", 0.13)))
    session_results = {}
    for session_name, session_cfg in pair_policy.items():
        if not isinstance(session_cfg, dict) or not session_cfg.get("enabled"):
            continue
        session_filter = build_session_filter(policy_root, session_name)
        segments = segmented_rows(frame, session_filter)
        policy = build_policy(session_cfg)
        risk = build_risk(config, session_cfg)
        runs = [run_segment(seg, policy, risk, pip_size, pip_value, session_filter.managed_close_minutes) for seg in segments if len(seg) >= 30]
        session_results[session_name] = {
            "segments": len(runs),
            "total_rows": sum(r["rows"] for r in runs),
            "buy_pnl": sum(r["buy_realized_pnl"] for r in runs),
            "sell_pnl": sum(r["sell_realized_pnl"] for r in runs),
            "sample": runs[:10],
            "policy": session_cfg,
        }
    return {"pair": pair, "missing_data": False, "sessions": session_results}


def main() -> int:
    args = parse_args()
    config = load_config()
    policy_root = load_json(POLICY_FILE)
    pairs = [p.upper() for p in args.pair] if args.pair else TARGET_PAIRS
    results = [run_pair(pair, config, policy_root, args.max_rows) for pair in pairs]
    payload = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "results": results}
    OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
