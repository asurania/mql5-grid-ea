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
OUTPUT_DIR = ROOT / "data" / "backtest" / "legacy_parity"
PRICE_DIR = ROOT / "data" / "processed" / "massive" / "fx_minute_bars"
TARGET_PAIRS = ["AUDNZD", "AUDUSD", "GBPJPY", "GBPUSD", "USDJPY", "NZDUSD", "AUDJPY"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run normalized legacy-grid parity backtests")
    parser.add_argument("--pair", action="append")
    parser.add_argument("--max-rows", type=int, default=12000)
    return parser.parse_args()


def load_price_frame(pair: str, max_rows: int) -> pl.DataFrame:
    paths = sorted(PRICE_DIR.glob('year=*/month=*/data.parquet'))
    if not paths:
        raise FileNotFoundError(f'No processed parquet partitions found under {PRICE_DIR}')
    return (
        pl.scan_parquet([str(p) for p in paths])
        .filter(pl.col("pair") == pair.upper())
        .select(["timestamp_utc", "open", "high", "low", "close"])
        .sort("timestamp_utc")
        .head(max_rows)
        .collect()
    )


def pair_step_windows(pair: str) -> tuple[TimeWindowConfig, ...]:
    if pair in {"GBPJPY", "AUDJPY", "USDJPY"}:
        return (
            TimeWindowConfig("16:00", "21:00", 5.0),
            TimeWindowConfig("21:00", "04:00", 3.0),
        )
    return (
        TimeWindowConfig("16:00", "21:00", 4.0),
        TimeWindowConfig("21:00", "04:00", 2.5),
    )


def pair_tp_windows(pair: str) -> tuple[TimeWindowConfig, ...]:
    if pair in {"GBPJPY", "AUDJPY", "USDJPY"}:
        return (
            TimeWindowConfig("16:00", "21:00", 4.5),
            TimeWindowConfig("21:00", "04:00", 3.5),
        )
    return (
        TimeWindowConfig("16:00", "21:00", 4.0),
        TimeWindowConfig("21:00", "04:00", 3.0),
    )


def build_policy_for_pair(pair: str) -> GridPolicy:
    jpy_pair = pair.endswith("JPY")
    return GridPolicy(
        step_mode="variable",
        fixed_step_pips=10.0 if not jpy_pair else 12.0,
        variable_steps_pips=(6.0, 6.0, 6.0, 6.0, 7.0, 7.0, 7.0, 8.5) if not jpy_pair else (8.0, 8.0, 8.0, 9.0, 10.0, 10.0, 12.0, 12.0),
        multiplier=1.15,
        initial_lot=0.01,
        max_lot=5.0,
        max_levels_buy=10,
        max_levels_sell=10,
        tp_pips_buy=4.0 if not jpy_pair else 5.0,
        tp_pips_sell=4.0 if not jpy_pair else 5.0,
        sl_pips=50.0 if not jpy_pair else 65.0,
        variable_ea=VariableEAConfig(
            enabled=True,
            mode="managed",
            step_windows=pair_step_windows(pair),
            tp_windows=pair_tp_windows(pair),
        ),
    )


def build_session_filter() -> SessionFilterConfig:
    return SessionFilterConfig(
        start_hhmm="16:00",
        stop_hhmm="04:00",
        managed_close_minutes=30,
        timezone_name="America/Edmonton",
        allowed_weekdays=(0, 1, 2, 3, 4),
        exempted_month_days=(3, 6, 8, 27),
    )


def build_risk(config: dict) -> NormalizedRiskLimits:
    equity = float(config["account"]["equity"])
    risk_mode = config["account"]["risk_mode"]
    account_dd = equity * float(config["risk"]["budget_pct"][risk_mode])
    basket_dd = equity * float(config["risk"]["max_basket_dd_pct"][risk_mode])
    basket_tp = equity * float(config["risk"]["target_profit_pct"][risk_mode])
    return NormalizedRiskLimits(
        account_equity=equity,
        max_account_drawdown_currency=round(account_dd, 2),
        max_basket_drawdown_currency=round(basket_dd, 2),
        target_basket_profit_currency=round(basket_tp, 2),
    )


def segmented_rows(frame: pl.DataFrame, session_filter: SessionFilterConfig) -> list[list[dict]]:
    segments: list[list[dict]] = []
    current: list[dict] = []
    for row in frame.iter_rows(named=True):
        ts = row["timestamp_utc"]
        if isinstance(ts, datetime):
            ts_utc = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        else:
            ts_utc = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
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
        ma_value = ma[idx]
        if ma_value is None:
            continue
        ts_utc = row["timestamp_utc"]
        managed_closing = ts_utc.timestamp() >= managed_cut
        snapshot = MarketSnapshot(
            timestamp_utc=ts_utc,
            bid=float(row["close"]),
            ask=float(row["close"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            ma_value=float(ma_value),
            gann_value=float(gann[idx]) if gann[idx] is not None else None,
        )
        engine.process_snapshot(snapshot, managed_closing=managed_closing)

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
        "managed_closing_only": engine.state.managed_closing_only,
        "breach_reason": engine.state.breach_reason,
    }


def run_pair(pair: str, config: dict, max_rows: int) -> dict:
    frame = load_price_frame(pair, max_rows)
    if frame.height == 0:
        return {"pair": pair, "segments": 0, "total_rows": 0, "missing_data": True}
    policy = build_policy_for_pair(pair)
    session_filter = build_session_filter()
    risk = build_risk(config)
    pip_size_map = config["pip_config"]["pip_size"]
    pip_value_map = config["pip_config"]["pip_value_per_001_lot"]
    pip_size = float(pip_size_map.get(pair, 0.01 if pair.endswith("JPY") else 0.0001))
    pip_value = float(pip_value_map.get(pair, pip_value_map.get("GBPUSD", 0.13)))
    segments = segmented_rows(frame, session_filter)
    segment_results = [run_segment(seg, policy, risk, pip_size, pip_value, session_filter.managed_close_minutes) for seg in segments if len(seg) >= 30]
    return {
        "pair": pair,
        "segments": len(segment_results),
        "total_rows": sum(r["rows"] for r in segment_results),
        "total_buy_realized_pnl": sum(r["buy_realized_pnl"] for r in segment_results),
        "total_sell_realized_pnl": sum(r["sell_realized_pnl"] for r in segment_results),
        "segment_results": segment_results[:10],
        "risk": asdict(risk),
        "missing_data": False,
    }


def main() -> int:
    args = parse_args()
    config = load_config()
    pairs = [p.upper() for p in args.pair] if args.pair else TARGET_PAIRS
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = [run_pair(pair, config, args.max_rows) for pair in pairs]
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    out = OUTPUT_DIR / "normalized_legacy_parity_7pair_summary.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
