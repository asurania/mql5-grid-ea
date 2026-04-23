from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

SIDE_BUY = "buy"
SIDE_SELL = "sell"
Side = Literal["buy", "sell"]
CALGARY_TZ = ZoneInfo("America/Edmonton")


@dataclass(frozen=True)
class LegacySignalConfig:
    ma_period: int = 21
    gann_period: int = 21
    gann_enabled: bool = True


@dataclass(frozen=True)
class TimeWindowConfig:
    start_hhmm: str
    stop_hhmm: str
    value: float


@dataclass(frozen=True)
class VariableEAConfig:
    enabled: bool = False
    mode: Literal["managed", "immediate"] = "managed"
    step_windows: tuple[TimeWindowConfig, ...] = ()
    tp_windows: tuple[TimeWindowConfig, ...] = ()


@dataclass(frozen=True)
class SessionFilterConfig:
    start_hhmm: str
    stop_hhmm: str
    managed_close_minutes: int = 30
    timezone_name: str = "America/Edmonton"
    allowed_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
    exempted_month_days: tuple[int, ...] = ()


@dataclass(frozen=True)
class NormalizedRiskLimits:
    account_equity: float
    max_account_drawdown_currency: float
    max_basket_drawdown_currency: float
    target_basket_profit_currency: float
    stop_trading_on_breach: bool = True


@dataclass(frozen=True)
class GridPolicy:
    step_mode: Literal["fixed", "variable"]
    fixed_step_pips: float
    variable_steps_pips: tuple[float, ...]
    multiplier: float
    initial_lot: float
    max_lot: float
    max_levels_buy: int
    max_levels_sell: int
    tp_pips_buy: float
    tp_pips_sell: float
    sl_pips: float | None
    variable_ea: VariableEAConfig = VariableEAConfig()


@dataclass(frozen=True)
class MarketSnapshot:
    timestamp_utc: datetime
    bid: float
    ask: float
    high: float
    low: float
    close: float
    ma_value: float
    gann_value: float | None


@dataclass(frozen=True)
class Order:
    side: Side
    lot: float
    entry_price: float
    opened_at_utc: datetime


@dataclass
class BasketState:
    side: Side
    orders: list[Order] = field(default_factory=list)
    realized_pnl_currency: float = 0.0
    closed: bool = False
    closed_reason: str | None = None
    active_step_pips: float | None = None
    active_tp_pips: float | None = None

    @property
    def count(self) -> int:
        return len(self.orders)

    @property
    def last_order(self) -> Order | None:
        return self.orders[-1] if self.orders else None

    @property
    def total_lots(self) -> float:
        return sum(order.lot for order in self.orders)

    @property
    def weighted_avg_entry(self) -> float | None:
        if not self.orders:
            return None
        total = self.total_lots
        if total <= 0:
            return None
        return sum(order.entry_price * order.lot for order in self.orders) / total


@dataclass
class SimulatorState:
    buy_basket: BasketState = field(default_factory=lambda: BasketState(side=SIDE_BUY))
    sell_basket: BasketState = field(default_factory=lambda: BasketState(side=SIDE_SELL))
    trading_enabled: bool = True
    breach_reason: str | None = None
    managed_closing_only: bool = False


class LegacyGridParityEngine:
    def __init__(self, policy: GridPolicy, risk: NormalizedRiskLimits, pip_size: float, pip_value_per_001_lot: float):
        self.policy = policy
        self.risk = risk
        self.pip_size = pip_size
        self.pip_value_per_001_lot = pip_value_per_001_lot
        self.state = SimulatorState()

    def process_snapshot(self, snapshot: MarketSnapshot, *, managed_closing: bool = False, force_flatten: bool = False) -> None:
        if force_flatten:
            self.close_all(snapshot, reason="forced_session_close")
            return
        self._apply_variable_ea(snapshot)
        if managed_closing:
            self.state.managed_closing_only = True
        if not self.state.trading_enabled:
            return
        if not self.state.managed_closing_only:
            self._maybe_open_seed(snapshot)
            self._maybe_expand(snapshot, self.state.buy_basket)
            self._maybe_expand(snapshot, self.state.sell_basket)
        self._maybe_take_profit_or_stop(snapshot, self.state.buy_basket)
        self._maybe_take_profit_or_stop(snapshot, self.state.sell_basket)
        self._evaluate_risk(snapshot)

    def close_all(self, snapshot: MarketSnapshot, reason: str) -> None:
        self._close_basket(snapshot, self.state.buy_basket, reason)
        self._close_basket(snapshot, self.state.sell_basket, reason)

    def _apply_variable_ea(self, snapshot: MarketSnapshot) -> None:
        ve = self.policy.variable_ea
        if not ve.enabled:
            return
        step_val = resolve_window_value(snapshot.timestamp_utc, ve.step_windows)
        tp_val = resolve_window_value(snapshot.timestamp_utc, ve.tp_windows)
        if ve.mode == "immediate":
            if step_val is not None:
                self.state.buy_basket.active_step_pips = step_val
                self.state.sell_basket.active_step_pips = step_val
            if tp_val is not None:
                self.state.buy_basket.active_tp_pips = tp_val
                self.state.sell_basket.active_tp_pips = tp_val
            return
        if self.state.buy_basket.count == 0:
            if step_val is not None:
                self.state.buy_basket.active_step_pips = step_val
            if tp_val is not None:
                self.state.buy_basket.active_tp_pips = tp_val
        if self.state.sell_basket.count == 0:
            if step_val is not None:
                self.state.sell_basket.active_step_pips = step_val
            if tp_val is not None:
                self.state.sell_basket.active_tp_pips = tp_val

    def _maybe_open_seed(self, snapshot: MarketSnapshot) -> None:
        if self.state.buy_basket.count == 0 and self._buy_signal(snapshot):
            self.state.buy_basket.orders.append(Order(SIDE_BUY, self.policy.initial_lot, snapshot.ask, snapshot.timestamp_utc))
        if self.state.sell_basket.count == 0 and self._sell_signal(snapshot):
            self.state.sell_basket.orders.append(Order(SIDE_SELL, self.policy.initial_lot, snapshot.bid, snapshot.timestamp_utc))

    def _maybe_expand(self, snapshot: MarketSnapshot, basket: BasketState) -> None:
        if basket.closed or basket.count == 0:
            return
        if basket.side == SIDE_BUY and self.policy.max_levels_buy and basket.count >= self.policy.max_levels_buy:
            return
        if basket.side == SIDE_SELL and self.policy.max_levels_sell and basket.count >= self.policy.max_levels_sell:
            return
        last = basket.last_order
        if last is None:
            return
        step = basket.active_step_pips if basket.active_step_pips is not None else self._current_step_pips(basket.count)
        trigger = last.entry_price - step * self.pip_size if basket.side == SIDE_BUY else last.entry_price + step * self.pip_size
        breached = snapshot.low <= trigger if basket.side == SIDE_BUY else snapshot.high >= trigger
        if not breached:
            return
        next_lot = min(last.lot * self.policy.multiplier, self.policy.max_lot) if basket.count > 0 else self.policy.initial_lot
        basket.orders.append(Order(basket.side, next_lot, trigger, snapshot.timestamp_utc))

    def _current_step_pips(self, step_index: int) -> float:
        if self.policy.step_mode == "fixed" or not self.policy.variable_steps_pips:
            return self.policy.fixed_step_pips
        idx = min(step_index - 1, len(self.policy.variable_steps_pips) - 1)
        return float(self.policy.variable_steps_pips[idx])

    def _buy_signal(self, snapshot: MarketSnapshot) -> bool:
        if snapshot.bid >= snapshot.ma_value:
            return False
        if snapshot.gann_value is None:
            return True
        return snapshot.bid < snapshot.gann_value

    def _sell_signal(self, snapshot: MarketSnapshot) -> bool:
        if snapshot.bid <= snapshot.ma_value:
            return False
        if snapshot.gann_value is None:
            return True
        return snapshot.bid > snapshot.gann_value

    def _maybe_take_profit_or_stop(self, snapshot: MarketSnapshot, basket: BasketState) -> None:
        if basket.closed or basket.count == 0:
            return
        avg = basket.weighted_avg_entry
        if avg is None:
            return
        tp_pips = basket.active_tp_pips if basket.active_tp_pips is not None else (self.policy.tp_pips_buy if basket.side == SIDE_BUY else self.policy.tp_pips_sell)
        tp_price = avg + tp_pips * self.pip_size if basket.side == SIDE_BUY else avg - tp_pips * self.pip_size
        tp_hit = snapshot.high >= tp_price if basket.side == SIDE_BUY else snapshot.low <= tp_price
        if tp_hit:
            self._close_basket(snapshot, basket, "basket_tp_pips", close_price=tp_price)
            return
        if self.policy.sl_pips is not None and self.policy.sl_pips > 0:
            sl_price = avg - self.policy.sl_pips * self.pip_size if basket.side == SIDE_BUY else avg + self.policy.sl_pips * self.pip_size
            sl_hit = snapshot.low <= sl_price if basket.side == SIDE_BUY else snapshot.high >= sl_price
            if sl_hit:
                self._close_basket(snapshot, basket, "basket_sl_pips", close_price=sl_price)
                return
        floating = self._basket_floating(snapshot, basket)
        if floating >= self.risk.target_basket_profit_currency:
            self._close_basket(snapshot, basket, "basket_tp_currency")
        elif -floating >= self.risk.max_basket_drawdown_currency:
            self._close_basket(snapshot, basket, "basket_drawdown_currency")

    def _close_basket(self, snapshot: MarketSnapshot, basket: BasketState, reason: str, close_price: float | None = None) -> None:
        if basket.count == 0:
            return
        px = close_price if close_price is not None else (snapshot.bid if basket.side == SIDE_BUY else snapshot.ask)
        basket.realized_pnl_currency += self._basket_pnl_at_price(px, basket)
        basket.orders.clear()
        basket.closed = True
        basket.closed_reason = reason
        basket.closed = False

    def _evaluate_risk(self, snapshot: MarketSnapshot) -> None:
        floating = self._floating_total(snapshot)
        if -floating >= self.risk.max_account_drawdown_currency:
            self.close_all(snapshot, reason="account_drawdown_limit")
            self.state.trading_enabled = False
            self.state.breach_reason = "account_drawdown_limit"

    def _floating_total(self, snapshot: MarketSnapshot) -> float:
        return self._basket_floating(snapshot, self.state.buy_basket) + self._basket_floating(snapshot, self.state.sell_basket)

    def _basket_pnl_at_price(self, price: float, basket: BasketState) -> float:
        pnl = 0.0
        for order in basket.orders:
            diff = price - order.entry_price if order.side == SIDE_BUY else order.entry_price - price
            pnl += (diff / self.pip_size) * self.pip_value_per_001_lot * (order.lot / 0.01)
        return pnl

    def _basket_floating(self, snapshot: MarketSnapshot, basket: BasketState) -> float:
        px = snapshot.bid if basket.side == SIDE_BUY else snapshot.ask
        return self._basket_pnl_at_price(px, basket)


def parse_hhmm(raw: str) -> tuple[int, int]:
    hh, mm = raw.split(":", 1)
    return int(hh), int(mm)


def is_time_in_window(ts_utc: datetime, start_hhmm: str, stop_hhmm: str, tz_name: str = "America/Edmonton") -> bool:
    local_tz = ZoneInfo(tz_name)
    local_dt = ts_utc.astimezone(local_tz)
    current = local_dt.hour * 60 + local_dt.minute
    start_h, start_m = parse_hhmm(start_hhmm)
    stop_h, stop_m = parse_hhmm(stop_hhmm)
    start = start_h * 60 + start_m
    stop = stop_h * 60 + stop_m
    if start <= stop:
        return start <= current < stop
    return current >= start or current < stop


def session_filter_allows(ts_utc: datetime, cfg: SessionFilterConfig) -> bool:
    local_tz = ZoneInfo(cfg.timezone_name)
    local_dt = ts_utc.astimezone(local_tz)
    if local_dt.weekday() not in cfg.allowed_weekdays:
        return False
    if local_dt.day in cfg.exempted_month_days:
        return False
    return is_time_in_window(ts_utc, cfg.start_hhmm, cfg.stop_hhmm, cfg.timezone_name)


def resolve_window_value(ts_utc: datetime, windows: tuple[TimeWindowConfig, ...], tz_name: str = "America/Edmonton") -> float | None:
    for window in windows:
        if is_time_in_window(ts_utc, window.start_hhmm, window.stop_hhmm, tz_name):
            return window.value
    return None


def compute_sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    run = 0.0
    for idx, value in enumerate(values):
        run += value
        if idx >= period:
            run -= values[idx - period]
        if idx + 1 >= period:
            out.append(run / period)
        else:
            out.append(None)
    return out


def compute_gann_hilo(highs: list[float], lows: list[float], closes: list[float], period: int) -> list[float | None]:
    high_sma = compute_sma(highs, period)
    low_sma = compute_sma(lows, period)
    out: list[float | None] = []
    for idx in range(len(closes)):
        if idx == 0 or high_sma[idx - 1] is None or low_sma[idx - 1] is None:
            out.append(None)
            continue
        if closes[idx] > float(high_sma[idx - 1]):
            out.append(float(low_sma[idx - 1]))
        elif closes[idx] < float(low_sma[idx - 1]):
            out.append(float(high_sma[idx - 1]))
        else:
            prev = out[idx - 1] if idx > 0 else None
            out.append(prev)
    return out


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
