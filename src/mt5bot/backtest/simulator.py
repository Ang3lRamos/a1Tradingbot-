"""Corre la misma estrategia, cálculo de lotes y filtro de riesgo del bot sobre velas históricas.

En cada vela la estrategia recibe la misma ventana de historial que recibe el bot en vivo.
Supuestos conservadores, para que el backtest no sea más optimista que la realidad:
- La entrada es a la apertura de la vela siguiente a la señal, comprando al ask (bid + spread).
- El spread es el de la vela de entrada, con spread_points como piso; la comisión se descuenta por lote.
- Si en una misma vela se tocan stop y target, se cuenta el stop.
- Si la vela abre con gap más allá del stop, la salida es a la apertura, no al stop.
- Breakeven y trailing se calculan al cierre de la vela y valen desde la siguiente, como en el bot.
- El cierre forzado (flat_by, viernes) se hace a la apertura de la primera vela a esa hora.
- La salida por regla de la estrategia se decide al cierre y se ejecuta a la apertura siguiente.
- Se descuenta el swap de cada noche con los datos del símbolo (triple el día que indica el broker).
"""
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from mt5bot.config import Settings
from mt5bot.core.costs import nights_charged, swap_per_night
from mt5bot.core.indicators import atr
from mt5bot.core.models import RiskState, SymbolSpec
from mt5bot.core.order_plan import plan_at_price
from mt5bot.core.position_rules import forced_close_reason, next_stop
from mt5bot.core.risk import evaluate
from mt5bot.core.strategies import get_strategy


@dataclass(frozen=True)
class Trade:
    entry_time: datetime
    side: str
    entry: float
    initial_stop: float
    target: float
    lots: float
    risk_money: float
    exit_time: datetime
    exit_price: float
    exit_reason: str
    pnl: float

    @property
    def r(self) -> float:
        return self.pnl / self.risk_money


@dataclass(frozen=True)
class BacktestResult:
    trades: list[Trade]
    blocked: list[tuple[datetime, list[str]]]


def run_backtest(symbol: str, bars: pd.DataFrame, spec: SymbolSpec, settings: Settings) -> BacktestResult:
    bars = bars.reset_index(drop=True)
    strategy = get_strategy(settings.strategy.name)
    window = strategy.bars_needed(settings.strategy)
    atr_values = atr(bars, settings.strategy.atr_period).to_numpy()
    equity = settings.backtest.initial_balance
    trades, blocked = [], []

    i = 0
    while i < len(bars) - 1:
        history = bars.iloc[max(0, i + 1 - window):i + 1]
        signal = strategy.find_signal(symbol, history, settings.strategy)
        if signal is None or signal.bar_time != history["time"].iloc[-1]:
            i += 1
            continue
        outcome, exit_index = _trade(signal, bars, i + 1, spec, settings, equity, atr_values)
        if isinstance(outcome, Trade):
            trades.append(outcome)
            equity += outcome.pnl
            i = exit_index  # al cierre de la vela de salida ya se puede buscar otra entrada
        else:
            blocked.append(outcome)
            i += 1
    return BacktestResult(trades=trades, blocked=blocked)


def _trade(signal, bars: pd.DataFrame, entry_index: int, spec, settings: Settings, equity: float, atr_values):
    entry_bar = bars.iloc[entry_index]
    entry_time = entry_bar["time"].to_pydatetime()
    bar_spread = int(entry_bar["spread"]) if "spread" in bars.columns else 0
    spread_points = max(settings.backtest.spread_points, bar_spread)
    spread = spread_points * spec.point

    fill = entry_bar["open"] + spread if signal.side == "buy" else entry_bar["open"]
    plan = plan_at_price(signal, fill, equity, settings.risk.risk_per_trade_pct, spec, settings.strategy.target_r)
    if plan is None:
        return (entry_time, ["el precio abrió más allá del stop"]), None

    state = RiskState(now=entry_time, balance_start_of_day=equity, equity=equity, pnl_today=0.0,
                      trades_today=0, open_positions=0, spread_points=spread_points)
    decision = evaluate(plan, state, settings.risk)
    if not decision.passed:
        return (entry_time, decision.reasons), None

    exit_index, exit_price, reason = _walk_to_exit(bars, entry_index, plan, spread, atr_values, settings)
    direction = plan.signal.direction
    exit_time = bars["time"].iloc[exit_index].to_pydatetime()
    gross = (exit_price - plan.signal.entry) * direction / spec.tick_size * spec.tick_value * plan.lots
    swap = swap_per_night(spec, direction, plan.signal.entry, plan.lots) * \
        nights_charged(entry_time, exit_time, spec.swap_triple_weekday)
    trade = Trade(
        entry_time=entry_time, side=signal.side, entry=plan.signal.entry,
        initial_stop=plan.signal.stop, target=plan.signal.target, lots=plan.lots,
        risk_money=plan.risk_money, exit_time=exit_time, exit_price=exit_price, exit_reason=reason,
        pnl=gross + swap - settings.backtest.commission_per_lot * plan.lots,
    )
    return trade, exit_index


def _walk_to_exit(bars: pd.DataFrame, start: int, plan, spread: float, atr_values: np.ndarray,
                  settings: Settings) -> tuple[int, float, str]:
    """Recorre las velas desde la de entrada hasta stop, target, regla de salida o cierre forzado."""
    signal, strategy = plan.signal, settings.strategy
    rules = get_strategy(strategy.name)
    window = rules.bars_needed(strategy)
    opened_at = bars["time"].iloc[start].to_pydatetime()
    direction = signal.direction
    stop = signal.stop
    # Las velas son de bid; una venta se cierra comprando al ask.
    offset = 0.0 if direction == 1 else spread
    exit_next_open = False

    for index, bar in enumerate(bars.iloc[start:].itertuples(index=False), start=start):
        if exit_next_open:
            return index, bar.open + offset, "regla"
        bar_open, high, low, close = bar.open + offset, bar.high + offset, bar.low + offset, bar.close + offset
        forced = forced_close_reason(bar.time, strategy.flat_by, settings.risk.friday_close)
        if forced:
            return index, bar_open, forced

        adverse, favorable = (low, high) if direction == 1 else (high, low)
        if (stop - adverse) * direction >= 0:
            gapped = (stop - bar_open) * direction > 0
            return index, bar_open if gapped else stop, "stop"
        if (favorable - signal.target) * direction >= 0:
            return index, signal.target, "target"

        moved = next_stop(direction, signal.entry, signal.stop, stop, close, atr_values[index],
                          strategy.breakeven_at_r, strategy.trail_atr)
        if moved is not None:
            stop = moved
        if rules.exit_due is not None:
            exit_next_open = rules.exit_due(bars.iloc[max(0, index + 1 - window):index + 1], opened_at, strategy)

    last = len(bars) - 1
    return last, bars["close"].iloc[last] + offset, "fin de datos"
