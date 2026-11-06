from dataclasses import replace

import pandas as pd
import pytest

from mt5bot.backtest.simulator import run_backtest
from mt5bot.core.indicators import atr
from mt5bot.core.strategy_donchian import bars_needed, find_signal

# Con 6 velas H4 por día desde un lunes 00:00, el índice 421 es lunes 04:00 y 439 es jueves 04:00:
# la entrada (vela siguiente) cae a las 08:00, dentro del horario de trading.
MONDAY_BREAKOUT, THURSDAY_BREAKOUT = 421, 439


def h4_bars(closes: list[float], start="2025-01-06 00:00") -> pd.DataFrame:
    """Velas H4 solo de lunes a viernes; open = cierre anterior, mechas de 5 pips."""
    times, t = [], pd.Timestamp(start)
    while len(times) < len(closes):
        if t.weekday() < 5:
            times.append(t)
        t += pd.Timedelta(hours=4)
    opens = [closes[0]] + closes[:-1]
    return pd.DataFrame({"time": times, "open": opens, "close": closes,
                         "high": [max(o, c) + 0.0005 for o, c in zip(opens, closes)],
                         "low": [min(o, c) - 0.0005 for o, c in zip(opens, closes)]})


def trend(n: int, step: float, start=1.10) -> list[float]:
    return [start + step * k for k in range(n)]


def no_costs(settings, **strategy):
    return replace(settings, strategy=replace(settings.strategy, **strategy),
                   backtest=replace(settings.backtest, spread_points=0, commission_per_lot=0))


def test_buy_on_breakout_in_uptrend(settings):
    closes = trend(MONDAY_BREAKOUT, 0.0001)
    closes.append(closes[-1] + 0.003)
    bars = h4_bars(closes)
    signal = find_signal("EURUSD", bars, settings.strategy)
    assert signal.side == "buy"
    risk = settings.strategy.donchian.stop_atr * atr(bars, settings.strategy.atr_period).iloc[-1]
    assert signal.stop == pytest.approx(closes[-1] - risk)


def test_steady_trend_without_breakout_gives_no_signal(settings):
    assert find_signal("EURUSD", h4_bars(trend(MONDAY_BREAKOUT + 1, 0.0001)), settings.strategy) is None


def test_breakout_against_the_trend_is_ignored(settings):
    closes = trend(MONDAY_BREAKOUT, -0.0001)
    closes.append(closes[-1] + 0.003)  # rompe el canal hacia arriba pero sigue bajo la EMA200
    assert find_signal("EURUSD", h4_bars(closes), settings.strategy) is None


def test_no_signal_without_enough_history(settings):
    closes = trend(bars_needed(settings.strategy) - 2, 0.0001)
    closes.append(closes[-1] + 0.003)
    assert find_signal("EURUSD", h4_bars(closes), settings.strategy) is None


def test_trailing_locks_profit_in_a_trend(settings, eurusd):
    closes = trend(MONDAY_BREAKOUT, 0.0001)
    closes.append(closes[-1] + 0.003)
    closes += [closes[-1] + 0.002 * k for k in range(1, 16)]     # tendencia fuerte
    closes += [closes[-1] - 0.004 * k for k in range(1, 4)]      # se da vuelta
    cfg = no_costs(settings, target_r=50.0)                      # sin objetivo: sale por trailing
    trade = run_backtest("EURUSD", h4_bars(closes), eurusd, cfg).trades[0]
    assert trade.exit_reason == "stop"
    assert trade.r > 3


def test_open_trade_is_closed_before_the_weekend(settings, eurusd):
    closes = trend(THURSDAY_BREAKOUT, 0.0001)
    closes.append(closes[-1] + 0.003)
    closes += [closes[-1]] * 12                                   # lateral hasta pasar el viernes
    trade = run_backtest("EURUSD", h4_bars(closes), eurusd, no_costs(settings)).trades[0]
    assert trade.exit_reason == "weekend"
    assert trade.entry_time == pd.Timestamp("2025-04-17 08:00")   # jueves
    assert trade.exit_time == pd.Timestamp("2025-04-18 20:00")    # viernes a friday_close


def test_backtest_does_not_look_ahead(settings, eurusd):
    closes = trend(THURSDAY_BREAKOUT, 0.0001)
    closes.append(closes[-1] + 0.003)
    closes += [closes[-1]] * 12
    bars = h4_bars(closes)
    cfg = no_costs(settings)
    full = run_backtest("EURUSD", bars, eurusd, cfg).trades
    cut = full[0].exit_time
    truncated = run_backtest("EURUSD", bars[bars["time"] <= cut], eurusd, cfg).trades
    assert truncated[0] == full[0]
