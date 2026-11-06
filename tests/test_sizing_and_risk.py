from dataclasses import replace
from datetime import datetime

import pytest

from mt5bot.core.models import OrderPlan, RiskState, Signal
from mt5bot.core.order_plan import plan_at_price
from mt5bot.core.risk import evaluate
from mt5bot.core.sizing import lots_for_risk


def test_lots_round_down_to_never_exceed_risk(eurusd):
    # 1000 USD al 1% = 10 USD; stop de 15 pips = 150 USD por lote -> 0.0666 -> 0.06
    assert lots_for_risk(10, 1.10000, 1.09850, eurusd) == 0.06


def test_lots_zero_when_min_lot_is_too_risky(eurusd):
    assert lots_for_risk(1, 1.10000, 1.09000, eurusd) == 0.0


def test_lots_capped_at_volume_max(eurusd):
    assert lots_for_risk(10_000_000, 1.10000, 1.09990, eurusd) == eurusd.volume_max


def test_equal_entry_and_stop_is_an_error(eurusd):
    with pytest.raises(ValueError):
        lots_for_risk(10, 1.1, 1.1, eurusd)


def signal(entry=1.1015, stop=1.1005, target=1.1030):
    return Signal("EURUSD", "buy", datetime(2026, 11, 2, 9, 0), entry, stop, target, "test")


def test_plan_keeps_stop_and_recomputes_target_at_fill(eurusd):
    plan = plan_at_price(signal(), 1.1017, 1000, 0.5, eurusd, target_r=1.5)
    assert plan.signal.stop == 1.1005
    assert plan.signal.target == pytest.approx(1.1017 + 1.5 * 0.0012)
    assert plan.risk_money <= 5.0


def test_plan_none_when_price_is_past_stop(eurusd):
    assert plan_at_price(signal(), 1.1004, 1000, 0.5, eurusd, 1.5) is None


def state(**overrides):
    base = RiskState(now=datetime(2026, 11, 2, 9, 0), balance_start_of_day=1000, equity=1000,
                     pnl_today=0, trades_today=0, open_positions=0, spread_points=8)
    return replace(base, **overrides)


def test_risk_passes_a_normal_order(settings):
    decision = evaluate(OrderPlan(signal(), 0.05, 5.0), state(), settings.risk)
    assert decision.passed, decision.reasons


def test_risk_blocks_when_order_could_breach_daily_loss(settings):
    # límite diario 2% = 20; ya perdidos 17 + 5 en riesgo = 22
    decision = evaluate(OrderPlan(signal(), 0.05, 5.0), state(pnl_today=-17), settings.risk)
    assert not decision.passed
    assert "pérdida del día" in decision.reasons[0]


def test_risk_reports_every_reason(settings):
    decision = evaluate(OrderPlan(signal(), 0.05, 5.0),
                        state(spread_points=50, trades_today=3, now=datetime(2026, 11, 2, 22, 0)),
                        settings.risk)
    assert len(decision.reasons) == 3


def test_risk_blocks_poor_reward_risk(settings):
    decision = evaluate(OrderPlan(signal(target=1.1020), 0.05, 5.0), state(), settings.risk)
    assert any("beneficio/riesgo" in r for r in decision.reasons)
