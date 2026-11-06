from dataclasses import replace
from datetime import datetime, time
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from mt5bot.backtest.simulator import run_backtest
from mt5bot.config import load_settings
from mt5bot.core.costs import nights_charged, swap_per_night
from mt5bot.core.models import SymbolSpec
from mt5bot.core.position_rules import forced_close_reason
from mt5bot.core.strategy_rsi2 import exit_due, find_signal
from mt5bot.engine import Bot
from mt5bot.io.journal import Journal
from tests.test_engine import FakeGateway

RSI2_CONFIG = Path(__file__).parents[1] / "config" / "rsi2.toml"
# Índice en USD: 1 lote = 10 x índice, 0.10 USD por tick de 0.01 (como US500.z en GNT).
INDEX = SymbolSpec(name="US500", digits=2, point=0.01, tick_size=0.01, tick_value=0.10, volume_min=0.01,
                   volume_max=100.0, volume_step=0.01, contract_size=10, swap_long=-9.3, swap_short=-9.8,
                   swap_mode=5, swap_triple_weekday=4)


@pytest.fixture
def rsi2_settings():
    s = load_settings(RSI2_CONFIG)
    return replace(s, backtest=replace(s.backtest, spread_points=0, commission_per_lot=0))


def daily_bars(closes: list[float], end="2025-12-05") -> pd.DataFrame:
    """Velas diarias de días hábiles que terminan en `end` (por defecto un viernes)."""
    times = pd.bdate_range(end=end, periods=len(closes))
    opens = [closes[0]] + closes[:-1]
    return pd.DataFrame({"time": times, "open": opens, "close": closes,
                         "high": [max(o, c) + 5 for o, c in zip(opens, closes)],
                         "low": [min(o, c) - 5 for o, c in zip(opens, closes)]})


def uptrend_then_dip(n: int) -> list[float]:
    closes = [6000 + 2 * k for k in range(n)]
    return closes + [closes[-1] - 40, closes[-1] - 90]          # dos días de caída fuerte


def test_buys_a_sharp_dip_in_an_uptrend(rsi2_settings):
    signal = find_signal("US500", daily_bars(uptrend_then_dip(240)), rsi2_settings.strategy)
    assert signal.side == "buy"
    assert signal.stop < signal.entry < signal.target


def test_no_signal_below_the_trend_mean(rsi2_settings):
    closes = [7000 - 2 * k for k in range(240)]
    closes += [closes[-1] - 40, closes[-1] - 90]
    assert find_signal("US500", daily_bars(closes), rsi2_settings.strategy) is None


def test_no_signal_without_enough_history(rsi2_settings):
    closes = uptrend_then_dip(rsi2_settings.strategy.rsi2.trend_sma + 20 - 5)
    assert find_signal("US500", daily_bars(closes), rsi2_settings.strategy) is None


def test_exit_when_close_is_back_over_the_short_mean(rsi2_settings):
    closes = uptrend_then_dip(240)
    bars = daily_bars(closes + [closes[-1] + 150])
    opened = bars["time"].iloc[-2].to_pydatetime()
    assert exit_due(bars, opened, rsi2_settings.strategy)
    assert not exit_due(bars.iloc[:-1], bars["time"].iloc[-1].to_pydatetime(), rsi2_settings.strategy)


def test_exit_after_max_bars(rsi2_settings):
    closes = uptrend_then_dip(240) + [5000 - k for k in range(12)]   # sigue cayendo: nunca cierra sobre la media
    bars = daily_bars(closes)
    opened = bars["time"].iloc[-rsi2_settings.strategy.rsi2.max_bars].to_pydatetime()
    assert exit_due(bars, opened, rsi2_settings.strategy)


def test_swap_percent_mode_per_night():
    # 1 lote de US500 a 7000 = 70.000 USD; -9.3 % anual / 360 = -18.08 USD por noche
    assert swap_per_night(INDEX, 1, 7000, 1.0) == pytest.approx(-70000 * 0.093 / 360)


def test_swap_points_mode():
    fx = SymbolSpec("EURUSD", 5, 0.00001, 0.00001, 1.0, 0.01, 100, 0.01, 100000, -6.5, 1.2, 1, 2)
    assert swap_per_night(fx, 1, 1.1, 2.0) == pytest.approx(-6.5 * 2)


def test_nights_triple_on_broker_day_and_none_on_weekend():
    # jueves -> lunes: noche del jueves (1) + viernes triple (3) = 4
    assert nights_charged(datetime(2026, 11, 5, 0, 5), datetime(2026, 11, 9, 0, 5), triple_weekday=4) == 4
    assert nights_charged(datetime(2026, 11, 5, 9), datetime(2026, 11, 5, 18), triple_weekday=4) == 0


def test_backtest_exits_next_open_and_pays_swap(rsi2_settings):
    closes = [6000 + 2 * k for k in range(240)]
    closes.append(closes[-1] - 60)                                    # una caída fuerte: señal al cierre
    closes += [closes[-1] + 10, closes[-1] + 80, closes[-1] + 90]     # rebota y cierra sobre la media de 5
    trade = run_backtest("US500", daily_bars(closes), INDEX, rsi2_settings).trades[0]
    assert trade.exit_reason == "regla"
    no_swap = replace(INDEX, swap_mode=0)
    free = run_backtest("US500", daily_bars(closes), no_swap, rsi2_settings).trades[0]
    assert trade.pnl < free.pnl


def test_engine_closes_on_exit_rule(rsi2_settings, tmp_path):
    closes = uptrend_then_dip(240)
    bars = daily_bars(closes + [closes[-1] + 150])
    journal = Journal(tmp_path / "j.db")
    opened = bars["time"].iloc[-2].to_pydatetime()
    plan = SimpleNamespace(signal=SimpleNamespace(symbol="US500", side="buy", entry=6400, stop=6200, target=7600),
                           lots=0.1, risk_money=200)
    journal.record_position(9, plan, opened)
    position = SimpleNamespace(ticket=9, symbol="US500", type="buy", price_open=6400, sl=6200, tp=7600)
    gateway = FakeGateway(INDEX, open_positions=[position], now=bars["time"].iloc[-1].to_pydatetime() + pd.Timedelta(days=1, minutes=1))
    gateway.closed_bars = lambda symbol, timeframe, count: bars
    Bot(gateway, rsi2_settings, journal).run_cycle("US500")
    journal.close()
    assert gateway.closed == [(9, "regla de salida")]


def with_sunday_stub(bars: pd.DataFrame) -> pd.DataFrame:
    """Agrega la vela D1 de 1 hora que GNT crea el domingo en la reapertura."""
    last = bars.iloc[-1]
    sunday = last["time"] + pd.Timedelta(days=(6 - last["time"].day_of_week) % 7 or 7)
    stub = {"time": sunday, "open": last["close"], "high": last["close"] + 1, "low": last["close"] - 1,
            "close": last["close"] + 0.5}
    return pd.concat([bars, pd.DataFrame([stub])], ignore_index=True)


def test_sunday_stub_bar_is_ignored(rsi2_settings):
    bars = daily_bars(uptrend_then_dip(240))
    friday_signal = find_signal("US500", bars, rsi2_settings.strategy)
    assert find_signal("US500", with_sunday_stub(bars), rsi2_settings.strategy) == friday_signal


def test_friday_signal_is_taken_when_the_market_reopens(rsi2_settings, tmp_path):
    bars = daily_bars(uptrend_then_dip(240))
    assert bars["time"].iloc[-1].day_of_week == 4                    # la señal es del viernes
    reopen = bars["time"].iloc[-1] + pd.Timedelta(days=2, hours=23)  # domingo 23:00
    journal = Journal(tmp_path / "j.db")
    gateway = FakeGateway(INDEX, now=reopen.to_pydatetime() + pd.Timedelta(minutes=2))
    gateway.closed_bars = lambda symbol, timeframe, count: bars
    gateway.forming = reopen.to_pydatetime()
    price = float(bars["close"].iloc[-1])
    gateway.quote = lambda symbol: (gateway.now, price, price + 0.3)
    gateway.balance_and_equity = lambda: (100000.0, 100000.0)  # con 1000 el lote mínimo de un índice no cabe
    live = replace(rsi2_settings, bot=replace(rsi2_settings.bot, mode="live"))
    Bot(gateway, live, journal).run_cycle("US500")
    journal.close()
    assert len(gateway.sent) == 1


def test_without_friday_close_positions_stay_over_the_weekend():
    assert forced_close_reason(datetime(2026, 11, 6, 21, 0), None, None) is None
    assert forced_close_reason(datetime(2026, 11, 6, 21, 0), None, time(20, 0)) == "weekend"
