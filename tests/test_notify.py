"""Avisos por Telegram: qué operaciones se avisan y que no se repitan."""
from datetime import datetime
from pathlib import Path

from mt5bot.config import load_settings
from mt5bot.main import notify_trades
from mt5bot.notify import pending_alerts
from mt5bot.report import BotView

CONFIG = Path(__file__).parents[1] / "config" / "settings.toml"

OPEN = {"ticket": 7, "symbol": "BTC/USD", "side": "buy", "volume": 0.00013, "price_open": 74300.0, "sl": 68000.0}
CLOSED = {"position": 5, "symbol": "USDCAD.z", "side": "buy", "opened": datetime(2026, 11, 6, 8),
          "closed": datetime(2026, 11, 6, 20), "entry": 1.4071, "exit": 1.4133, "pnl": 629.45, "r": 1.27}


def bot(open_positions=(), trades=()):
    return BotView(name="Bot RSI2", description="", expected=load_settings(CONFIG).backtest, trades=list(trades),
                   open_positions=list(open_positions), events=[], status="", magic=260514)


def test_new_open_and_closed_trades_are_alerted_once():
    alerts = pending_alerts([bot([OPEN], [CLOSED])], set())
    assert [key for key, _ in alerts] == ["260514-open-7", "260514-close-5"]
    assert "Compra BTC/USD" in alerts[0][1] and "stop 68,000.00" in alerts[0][1]
    assert "+629.45 USD (+1.27 R)" in alerts[1][1]
    assert pending_alerts([bot([OPEN], [CLOSED])], {key for key, _ in alerts}) == []


def test_first_run_records_old_trades_without_sending(tmp_path, monkeypatch):
    sent_messages = []
    monkeypatch.setattr("mt5bot.main.ALERTS_PATH", tmp_path / "sent.json")
    monkeypatch.setattr("mt5bot.io.telegram.send", lambda token, chat, text: sent_messages.append(text))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    notify_trades([bot(trades=[CLOSED])])
    assert sent_messages == []                        # lo que ya había no se avisa
    notify_trades([bot([OPEN], [CLOSED])])
    assert len(sent_messages) == 1 and "BTC/USD" in sent_messages[0]
