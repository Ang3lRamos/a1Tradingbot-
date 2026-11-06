from dataclasses import replace

import pytest

from mt5bot.backtest.metrics import monte_carlo, summarize
from mt5bot.backtest.simulator import run_backtest
from tests.conftest import make_bars, range_rows

DAY = "2026-11-02"
BREAKOUT = ("09:00", 1.1005, 1.1016, 1.1005, 1.1015)


def no_costs(settings):
    return replace(settings, backtest=replace(settings.backtest, spread_points=0, commission_per_lot=0))


def run(settings, eurusd, rows):
    return run_backtest("EURUSD", make_bars(DAY, range_rows() + [BREAKOUT] + rows), eurusd, no_costs(settings))


def test_target_hit(orb_settings, eurusd):
    # entrada 1.1015, stop 1.1005 (10 pips), target 1.1030
    result = run(orb_settings, eurusd, [("09:15", 1.1015, 1.1018, 1.1012, 1.1016),
                                        ("09:30", 1.1016, 1.1031, 1.1014, 1.1028)])
    trade = result.trades[0]
    assert trade.exit_reason == "target"
    assert trade.r == pytest.approx(1.5, rel=0.01)


def test_stop_counts_first_when_bar_touches_both(orb_settings, eurusd):
    result = run(orb_settings, eurusd, [("09:15", 1.1015, 1.1031, 1.1004, 1.1020)])
    assert result.trades[0].exit_reason == "stop"
    assert result.trades[0].r == pytest.approx(-1, rel=0.01)


def test_gap_through_stop_fills_at_open(orb_settings, eurusd):
    result = run(orb_settings, eurusd, [("09:15", 1.1015, 1.1016, 1.1012, 1.1013),
                                        ("09:30", 1.1000, 1.1002, 1.0995, 1.0998)])
    trade = result.trades[0]
    assert trade.exit_price == 1.1000
    assert trade.r < -1


def test_breakeven_turns_reversal_into_scratch(orb_settings, eurusd):
    result = run(orb_settings, eurusd, [("09:15", 1.1015, 1.1026, 1.1014, 1.1025),   # cierra en +1R
                                        ("09:30", 1.1024, 1.1025, 1.1000, 1.1002)])  # se devuelve
    trade = result.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.pnl == pytest.approx(0, abs=1e-9)


def test_breakeven_uses_the_close_not_the_wick(orb_settings, eurusd):
    # La mecha llega a +1.1R pero cierra en +0.9R: como el bot, no mueve el stop.
    result = run(orb_settings, eurusd, [("09:15", 1.1015, 1.1026, 1.1014, 1.1024),
                                        ("09:30", 1.1024, 1.1025, 1.1000, 1.1002)])
    assert result.trades[0].r == pytest.approx(-1, rel=0.01)


def test_flat_by_closes_open_trade(orb_settings, eurusd):
    result = run(orb_settings, eurusd, [("09:15", 1.1015, 1.1018, 1.1012, 1.1016),
                                        ("20:00", 1.1019, 1.1020, 1.1018, 1.1019)])
    assert result.trades[0].exit_reason == "flat_by"
    assert result.trades[0].exit_price == 1.1019


def test_spread_is_paid_on_entry(orb_settings, eurusd):
    rows = range_rows() + [BREAKOUT, ("09:15", 1.1015, 1.1018, 1.1012, 1.1016)]
    trade = run_backtest("EURUSD", make_bars(DAY, rows), eurusd, orb_settings).trades[0]
    assert trade.entry == pytest.approx(1.1015 + orb_settings.backtest.spread_points * eurusd.point)


def test_commission_is_charged_per_lot(orb_settings, eurusd):
    rows = [("09:15", 1.1015, 1.1018, 1.1012, 1.1016), ("09:30", 1.1016, 1.1031, 1.1014, 1.1028)]
    free = run(orb_settings, eurusd, rows).trades[0]
    cfg = replace(no_costs(orb_settings), backtest=replace(no_costs(orb_settings).backtest, commission_per_lot=10))
    paid = run_backtest("EURUSD", make_bars(DAY, range_rows() + [BREAKOUT] + rows), eurusd, cfg).trades[0]
    assert free.pnl - paid.pnl == pytest.approx(10 * paid.lots)


def test_metrics_and_monte_carlo_are_reproducible():
    r_values = [1.5, -1, -1, 1.5, 0, -1, 1.5, 1.5, -1, -1]
    first = monte_carlo(r_values, 0.5, runs=2000, seed=19)
    assert first == monte_carlo(r_values, 0.5, runs=2000, seed=19)
    assert first["return_pct"]["p5"] <= first["return_pct"]["p50"] <= first["return_pct"]["p95"]


def test_summarize_empty():
    assert summarize([], 1000) == {"trades": 0}
