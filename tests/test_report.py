from dataclasses import replace
from datetime import datetime

import pytest

from mt5bot.report import AccountView, BotView, closed_trades, liveness, render, summary, verdict

T0 = datetime(2026, 11, 6, 12, 0)


def deal(position, entry, side, price, volume, money, minute=0):
    return {"position": position, "symbol": "USDCAD.z", "time": T0.replace(minute=minute), "entry": entry,
            "side": side, "price": price, "volume": volume, "money": money}


INFO = {1: {"risk_money": 500.0, "initial_stop": 1.40}, 2: {"risk_money": 500.0, "initial_stop": 1.41}}


def test_closed_trade_includes_commission_and_r():
    deals = [deal(1, True, "buy", 1.406, 1.34, -13.4), deal(1, False, "sell", 1.410, 1.34, 380.0, minute=30)]
    trade = closed_trades(deals, INFO)[0]
    assert trade["pnl"] == pytest.approx(366.6)
    assert trade["r"] == pytest.approx(366.6 / 500)
    assert trade["side"] == "buy"


def test_open_or_partially_closed_positions_are_not_counted():
    deals = [deal(1, True, "buy", 1.406, 1.0, -10.0),
             deal(2, True, "sell", 1.40, 1.0, -10.0), deal(2, False, "buy", 1.39, 0.5, 50.0, minute=5)]
    assert closed_trades(deals, INFO) == []


def test_trade_without_journal_risk_has_no_r():
    deals = [deal(9, True, "buy", 1.4, 1.0, -10), deal(9, False, "sell", 1.41, 1.0, 100, minute=1)]
    assert closed_trades(deals, INFO)[0]["r"] is None


def test_summary_and_verdict_need_enough_trades(settings):
    trades = [{"pnl": 100.0, "r": 0.2}, {"pnl": -500.0, "r": -1.0}]
    stats = summary(trades)
    assert stats["n"] == 2 and stats["win_rate"] == 50 and stats["avg_r"] == pytest.approx(-0.4)
    assert "muy pocas" in verdict(stats, settings.backtest)
    many = summary([{"pnl": 10.0, "r": settings.backtest.expected_avg_r}] * 40)
    assert verdict(many, settings.backtest) == "Se comporta como dice el backtest."


def test_liveness_from_heartbeat():
    assert "Activo" in liveness(datetime(2026, 11, 6, 12, 0), datetime(2026, 11, 6, 12, 2))
    assert "SIN LATIDO" in liveness(datetime(2026, 11, 6, 9, 0), datetime(2026, 11, 6, 12, 0))
    assert "Sin latido" in liveness(None, datetime(2026, 11, 6, 12, 0))


def test_render_contains_each_bot(settings):
    bot = BotView(name="Bot <Donchian>", description="H4", expected=settings.backtest, trades=[],
                  open_positions=[], events=[], status="🟢 Activo")
    accounts = [AccountView("Demo GNT", 100000.0, 100216.59), AccountView("Alpaca", None, None, "sin llaves")]
    page = render([bot, replace(bot, name="Bot RSI2")], accounts, T0)
    assert "Bot &lt;Donchian&gt;" in page and "Bot RSI2" in page   # el texto se escapa
    assert "+216.59" in page and "Sin conexión: sin llaves" in page
    assert 'http-equiv="refresh"' in page                         # el navegador recarga la página sola
