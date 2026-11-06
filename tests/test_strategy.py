from dataclasses import replace

import pandas as pd
import pytest

from mt5bot.core.position_rules import next_stop
from mt5bot.core.strategy_orb import find_signal
from tests.conftest import make_bars, range_rows

DAY = "2026-11-02"


def test_buy_on_first_close_above_range(orb_settings):
    bars = make_bars(DAY, range_rows() + [("09:00", 1.1005, 1.1008, 1.1003, 1.1006),
                                          ("09:15", 1.1006, 1.1016, 1.1005, 1.1015)])
    signal = find_signal("EURUSD", bars, orb_settings.strategy)
    assert signal.side == "buy"
    assert signal.entry == 1.1015
    assert signal.stop == pytest.approx(1.1005)  # mitad del rango
    assert signal.target == pytest.approx(1.1015 + 1.5 * 0.0010)


def test_sell_with_stop_at_range_opposite(orb_settings):
    strategy = orb_settings.strategy
    cfg = replace(strategy, orb=replace(strategy.orb, stop_mode="range_opposite"))
    bars = make_bars(DAY, range_rows() + [("09:00", 1.1003, 1.1004, 1.0990, 1.0995)])
    signal = find_signal("EURUSD", bars, cfg)
    assert signal.side == "sell"
    assert signal.stop == 1.1010


def test_no_signal_inside_range(orb_settings):
    bars = make_bars(DAY, range_rows() + [("09:00", 1.1005, 1.1009, 1.1001, 1.1006)])
    assert find_signal("EURUSD", bars, orb_settings.strategy) is None


def test_no_signal_when_first_breakout_is_after_entry_until(orb_settings):
    bars = make_bars(DAY, range_rows() + [("12:00", 1.1005, 1.1016, 1.1005, 1.1015)])
    assert find_signal("EURUSD", bars, orb_settings.strategy) is None


def test_only_first_breakout_counts_and_no_lookahead(orb_settings):
    first = range_rows() + [("09:00", 1.1005, 1.1016, 1.1005, 1.1015)]
    later = first + [("09:15", 1.1015, 1.1016, 1.0980, 1.0985)]
    assert find_signal("EURUSD", make_bars(DAY, first), orb_settings.strategy) == \
        find_signal("EURUSD", make_bars(DAY, later), orb_settings.strategy)


def test_only_the_last_day_is_used(orb_settings):
    yesterday = make_bars("2026-11-01", range_rows() + [("09:00", 1.1005, 1.1016, 1.1005, 1.1015)])
    today = make_bars(DAY, range_rows())
    assert find_signal("EURUSD", pd.concat([yesterday, today], ignore_index=True), orb_settings.strategy) is None


@pytest.mark.parametrize("price, current_stop, trail_atr, expected", [
    (1.1020, 1.1000, 0, 1.1010),        # +1R con stop original: a breakeven
    (1.1015, 1.1000, 0, None),          # +0.5R: no se mueve
    (1.1020, 1.1010, 0, None),          # ya en breakeven
    (1.1050, 1.1000, 2, 1.1030),        # +4R: trailing a 2 x ATR(0.0010) por encima del breakeven
    (1.1025, 1.1030, 2, None),          # el trailing nunca afloja el stop
])
def test_next_stop(price, current_stop, trail_atr, expected):
    moved = next_stop(1, 1.1010, 1.1000, current_stop, price, 0.0010, 1.0, trail_atr)
    assert moved == (pytest.approx(expected) if expected is not None else None)


def test_next_stop_for_sells():
    # venta en 1.1010, stop 1.1020; precio 1.0970 = +4R; trailing 2 x 0.0010 = 1.0990
    assert next_stop(-1, 1.1010, 1.1020, 1.1020, 1.0970, 0.0010, 1.0, 2) == pytest.approx(1.0990)
