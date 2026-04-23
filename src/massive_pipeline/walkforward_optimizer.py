from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeometryCandidate:
    grid_level: int
    multiplier: float
    step_pips: float
    basket_tp_pips: float


@dataclass(frozen=True)
class RiskCandidate:
    initial_lot: float
    profit_target_currency: float | None
    max_dd_currency: float


@dataclass(frozen=True)
class CandidateEvaluation:
    enabled: bool
    geometry: GeometryCandidate | None
    risk: RiskCandidate | None
    training_sessions_used: int
    total_pnl: float
    max_drawdown: float
    worst_session_loss: float
    stopout_count: int
    forced_close_count: int
    score: float
    reject_reason: str | None = None


def load_candidate_config(path: str) -> dict[str, Any]:
    import json
    from pathlib import Path

    return json.loads(Path(path).read_text())


def generate_geometry_candidates(config: dict[str, Any]):
    for grid_level, multiplier, step_pips, basket_tp_pips in itertools.product(
        config["grid_level"],
        config["multiplier"],
        config["step_pips"],
        config["basket_tp_pips"],
    ):
        yield GeometryCandidate(
            grid_level=int(grid_level),
            multiplier=float(multiplier),
            step_pips=float(step_pips),
            basket_tp_pips=float(basket_tp_pips),
        )


def generate_risk_candidates(config: dict[str, Any]):
    for initial_lot, profit_target_currency, max_dd_currency in itertools.product(
        config["initial_lot"],
        config["profit_target_currency"],
        config["max_dd_currency"],
    ):
        yield RiskCandidate(
            initial_lot=float(initial_lot),
            profit_target_currency=None if profit_target_currency is None else float(profit_target_currency),
            max_dd_currency=float(max_dd_currency),
        )


def score_candidate(
    *,
    total_pnl: float,
    max_drawdown: float,
    worst_session_loss: float,
    stopout_count: int,
    forced_close_count: int,
) -> float:
    return (
        total_pnl
        - 1.5 * max_drawdown
        - 25.0 * stopout_count
        - 0.5 * abs(worst_session_loss)
        - 10.0 * forced_close_count
    )


def candidate_passes(
    *,
    training_sessions_used: int,
    max_drawdown: float,
    max_dd_currency: float,
    stopout_count: int,
    forced_close_count: int,
    min_training_sessions: int,
    max_stopouts: int = 4,
    max_forced_closes: int = 8,
) -> tuple[bool, str | None]:
    if training_sessions_used < min_training_sessions:
        return False, "insufficient_training_sessions"
    if max_drawdown > max_dd_currency:
        return False, "drawdown_cap_breached"
    if stopout_count > max_stopouts:
        return False, "too_many_stopouts"
    if forced_close_count > max_forced_closes:
        return False, "too_many_forced_closes"
    return True, None


def disabled_evaluation(reason: str) -> CandidateEvaluation:
    return CandidateEvaluation(
        enabled=False,
        geometry=None,
        risk=None,
        training_sessions_used=0,
        total_pnl=0.0,
        max_drawdown=0.0,
        worst_session_loss=0.0,
        stopout_count=0,
        forced_close_count=0,
        score=float("-inf"),
        reject_reason=reason,
    )
