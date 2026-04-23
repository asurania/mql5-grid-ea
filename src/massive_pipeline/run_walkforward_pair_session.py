from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from massive_pipeline.backtest_grid_policy import (
    DEFAULT_CONFIG,
    DEFAULT_EVENT_GATING_PATH,
    DEFAULT_GRID_POLICY,
    PRICE_DIR,
    PolicyOverrides,
    build_backtest_context,
    load_json,
    load_live_pair_policies,
    resolve_account_settings,
    run_session_backtest,
)
from massive_pipeline.trading_config import load_config
from massive_pipeline.walkforward_optimizer import (
    candidate_passes,
    disabled_evaluation,
    generate_geometry_candidates,
    generate_risk_candidates,
    load_candidate_config,
    score_candidate,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_CONFIG = ROOT / "config" / "walkforward_candidate_space_v1.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "backtest" / "walkforward_v1"
UTC = timezone.utc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Weekly walk-forward optimizer scaffold for pair x session grid policies.")
    parser.add_argument("--pair", action="append", required=True)
    parser.add_argument("--session", action="append", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--lookback-days", type=int, default=28)
    parser.add_argument("--forward-days", type=int, default=7)
    parser.add_argument("--account-equity", type=float, default=10000.0)
    parser.add_argument("--candidate-config", type=Path, default=DEFAULT_CANDIDATE_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--grid-policy", type=Path, default=DEFAULT_GRID_POLICY)
    parser.add_argument("--event-path", type=Path, default=DEFAULT_EVENT_GATING_PATH)
    parser.add_argument("--use-live-policy", action="store_true", default=True)
    parser.add_argument("--session-filter", default="all")
    parser.add_argument("--exclude-event-gated-from-training", action="store_true", default=True)
    return parser.parse_args()


def daterange(start_day: date, end_day: date, step_days: int):
    current = start_day
    while current < end_day:
        yield current
        current += timedelta(days=step_days)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    candidate_config = load_candidate_config(str(args.candidate_config))
    config = load_json(args.config) if args.config != DEFAULT_CONFIG else load_config()
    live_pair_policies = load_live_pair_policies(args.grid_policy) if args.use_live_policy else {}
    risk_mode, account_equity = resolve_account_settings(config, None, args.account_equity)

    start_day = date.fromisoformat(args.start_date)
    end_day = date.fromisoformat(args.end_date)
    rebalance_days = list(daterange(start_day, end_day, args.forward_days))

    policy_rows: list[dict[str, Any]] = []
    forward_rows: list[dict[str, Any]] = []

    for rebalance_day in rebalance_days:
        training_start = rebalance_day - timedelta(days=args.lookback_days)
        forward_end = min(end_day, rebalance_day + timedelta(days=args.forward_days))

        for pair in args.pair:
            for session in args.session:
                session_specs, bars, event_gates = build_backtest_context(
                    pairs=[pair],
                    config=config,
                    live_pair_policies=live_pair_policies,
                    session_filter=session,
                    start_date=training_start,
                    end_date=rebalance_day - timedelta(days=1),
                    policy_id_override=None,
                    risk_mode=risk_mode,
                    account_equity=account_equity,
                    use_live_policy=args.use_live_policy,
                    overrides=PolicyOverrides(),
                    price_root=PRICE_DIR,
                    event_path=args.event_path,
                )
                if args.exclude_event_gated_from_training:
                    session_specs = [
                        spec for spec in session_specs if (spec.pair, spec.session_name, spec.session_start_utc.date()) not in event_gates
                    ]

                top_geometry: list[tuple[float, Any, dict[str, Any]]] = []
                for geometry in generate_geometry_candidates(candidate_config):
                    overrides = PolicyOverrides(
                        step_pips=geometry.step_pips,
                        max_trades_per_side=geometry.grid_level,
                        basket_tp_pips=geometry.basket_tp_pips,
                        multiplier=geometry.multiplier,
                    )
                    geometry_specs, _, _ = build_backtest_context(
                        pairs=[pair],
                        config=config,
                        live_pair_policies=live_pair_policies,
                        session_filter=session,
                        start_date=training_start,
                        end_date=rebalance_day - timedelta(days=1),
                        policy_id_override=None,
                        risk_mode=risk_mode,
                        account_equity=account_equity,
                        use_live_policy=args.use_live_policy,
                        overrides=overrides,
                        price_root=PRICE_DIR,
                        event_path=args.event_path,
                    )
                    if args.exclude_event_gated_from_training:
                        geometry_specs = [
                            spec for spec in geometry_specs if (spec.pair, spec.session_name, spec.session_start_utc.date()) not in event_gates
                        ]
                    training_results = run_session_backtest(
                        session_specs=geometry_specs,
                        bars=bars,
                        event_risk_gated_sessions=event_gates,
                        use_event_risk_gating=False,
                        use_entry_intent_gating=False,
                    )
                    total_pnl = sum(row.realized_pnl for row in training_results)
                    max_drawdown = max((row.max_drawdown for row in training_results), default=0.0)
                    worst_session_loss = min((row.realized_pnl for row in training_results), default=0.0)
                    stopout_count = sum(1 for row in training_results if row.exit_reason == "drawdown_limit")
                    forced_close_count = sum(1 for row in training_results if row.exit_reason in {"session_close", "daily_liquidation"})
                    training_sessions_used = len(training_results)
                    candidate_score = score_candidate(
                        total_pnl=total_pnl,
                        max_drawdown=max_drawdown,
                        worst_session_loss=worst_session_loss,
                        stopout_count=stopout_count,
                        forced_close_count=forced_close_count,
                    )
                    top_geometry.append((candidate_score, geometry, {
                        "training_sessions_used": training_sessions_used,
                        "total_pnl": total_pnl,
                        "max_drawdown": max_drawdown,
                        "worst_session_loss": worst_session_loss,
                        "stopout_count": stopout_count,
                        "forced_close_count": forced_close_count,
                    }))
                top_geometry.sort(key=lambda item: item[0], reverse=True)
                top_geometry = top_geometry[: int(candidate_config.get("stage_a_top_n", 20))]

                best_row: dict[str, Any] | None = None
                best_score = float("-inf")
                for _, geometry, geom_metrics in top_geometry:
                    for risk in generate_risk_candidates(candidate_config):
                        passed, reject_reason = candidate_passes(
                            training_sessions_used=geom_metrics["training_sessions_used"],
                            max_drawdown=geom_metrics["max_drawdown"],
                            max_dd_currency=risk.max_dd_currency,
                            stopout_count=geom_metrics["stopout_count"],
                            forced_close_count=geom_metrics["forced_close_count"],
                            min_training_sessions=int(candidate_config.get("min_training_sessions", 8)),
                        )
                        if not passed:
                            continue
                        candidate_total_score = geom_metrics["total_pnl"] - (0.0 if risk.profit_target_currency is None else 0.01 * risk.profit_target_currency)
                        if candidate_total_score > best_score:
                            best_score = candidate_total_score
                            best_row = {
                                "rebalance_date": rebalance_day.isoformat(),
                                "training_start": training_start.isoformat(),
                                "training_end": (rebalance_day - timedelta(days=1)).isoformat(),
                                "pair": pair,
                                "session": session,
                                "enabled": True,
                                "initial_lot": risk.initial_lot,
                                "grid_level": geometry.grid_level,
                                "multiplier": geometry.multiplier,
                                "step_pips": geometry.step_pips,
                                "basket_tp_pips": geometry.basket_tp_pips,
                                "profit_target_currency": risk.profit_target_currency,
                                "max_dd_currency": risk.max_dd_currency,
                                "training_sessions_used": geom_metrics["training_sessions_used"],
                                "training_total_pnl": round(geom_metrics["total_pnl"], 6),
                                "training_max_dd": round(geom_metrics["max_drawdown"], 6),
                                "training_score": round(candidate_total_score, 6),
                            }
                if best_row is None:
                    best_row = {
                        "rebalance_date": rebalance_day.isoformat(),
                        "training_start": training_start.isoformat(),
                        "training_end": (rebalance_day - timedelta(days=1)).isoformat(),
                        "pair": pair,
                        "session": session,
                        "enabled": False,
                        "reject_reason": "no_candidate_passed_filters",
                    }
                policy_rows.append(best_row)
                if best_row.get("enabled", False):
                    forward_overrides = PolicyOverrides(
                        step_pips=best_row.get("step_pips"),
                        max_trades_per_side=best_row.get("grid_level"),
                        initial_lot=best_row.get("initial_lot"),
                        basket_tp_pips=best_row.get("basket_tp_pips"),
                        multiplier=best_row.get("multiplier"),
                        max_basket_drawdown_currency=best_row.get("max_dd_currency"),
                        basket_tp_currency=best_row.get("profit_target_currency"),
                    )
                    forward_specs, forward_bars, forward_event_gates = build_backtest_context(
                        pairs=[pair],
                        config=config,
                        live_pair_policies=live_pair_policies,
                        session_filter=session,
                        start_date=rebalance_day,
                        end_date=forward_end - timedelta(days=1),
                        policy_id_override=None,
                        risk_mode=risk_mode,
                        account_equity=account_equity,
                        use_live_policy=args.use_live_policy,
                        overrides=forward_overrides,
                        price_root=PRICE_DIR,
                        event_path=args.event_path,
                    )
                    forward_results = run_session_backtest(
                        session_specs=forward_specs,
                        bars=forward_bars,
                        event_risk_gated_sessions=forward_event_gates,
                        use_event_risk_gating=True,
                        use_entry_intent_gating=False,
                    )
                    forward_total_pnl = sum(row.realized_pnl for row in forward_results)
                    forward_max_dd = max((row.max_drawdown for row in forward_results), default=0.0)
                    forward_trade_count = sum(row.trade_count for row in forward_results)
                    forward_rows.append(
                        {
                            "week_start": rebalance_day.isoformat(),
                            "week_end": forward_end.isoformat(),
                            "pair": pair,
                            "session": session,
                            "enabled": True,
                            "forward_total_pnl": round(forward_total_pnl, 6),
                            "forward_max_dd": round(forward_max_dd, 6),
                            "forward_trade_count": forward_trade_count,
                            "forward_event_gated_sessions": sum(1 for row in forward_results if row.gated_by_event_risk),
                            "forward_status": "ok",
                        }
                    )
                else:
                    forward_rows.append(
                        {
                            "week_start": rebalance_day.isoformat(),
                            "week_end": forward_end.isoformat(),
                            "pair": pair,
                            "session": session,
                            "enabled": False,
                            "forward_status": "disabled",
                        }
                    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "policy_history.csv", policy_rows)
    write_csv(args.output_dir / "forward_results.csv", forward_rows)
    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "pairs": args.pair,
        "sessions": args.session,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "lookback_days": args.lookback_days,
        "forward_days": args.forward_days,
        "candidate_config": str(args.candidate_config),
        "status": "training_selection_wired_forward_run_pending",
    }
    (args.output_dir / "overall_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
