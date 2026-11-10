"""Avisos por Telegram: operaciones, errores, bots caídos y brokers sin respuesta, sin repetir."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from mt5bot.config import load_settings
from mt5bot.main import notify
from mt5bot.notify import AlertState, pending_alerts
from mt5bot.report import AccountView, BotView

CONFIG = Path(__file__).parents[1] / "config" / "settings.toml"
NOW = datetime(2026, 11, 9, 19, 5)
OPEN = {"ticket": 7, "symbol": "BTC/USD", "side": "buy", "volume": 0.00013, "price_open": 74300.0, "sl": 68000.0}
CLOSED = {"position": 5, "symbol": "USDCAD.z", "side": "buy", "opened": datetime(2026, 11, 6, 8),
          "closed": datetime(2026, 11, 6, 20), "entry": 1.4071, "exit": 1.4133, "pnl": 629.45, "r": 1.27}
ERROR = {"logged_at": "2026-11-09T06:36:26", "server_time": None, "symbol": "BTC/USD", "kind": "error",
         "detail": {"message": "Alpaca: Connection aborted."}}
ALPACA_OK, ALPACA_DOWN = AccountView("Alpaca", 100.0, 100.0), AccountView("Alpaca", None, None, "Read timed out")


def bot(open_positions=(), trades=(), events=(), last_beat=NOW):
    return BotView(name="Bot RSI2", description="", expected=load_settings(CONFIG).backtest, trades=list(trades),
                   open_positions=list(open_positions), events=list(events), status="", magic=260514,
                   last_beat=last_beat)


def test_new_open_and_closed_trades_are_alerted_once():
    messages, state = pending_alerts([bot([OPEN], [CLOSED])], [], AlertState(), NOW)
    assert len(messages) == 2
    assert "<b>Compra BTC/USD</b>" in messages[0] and "Stop: 68,000.00 (-8.48 %)" in messages[0]
    assert "Ganancia +629.45 USD · +1.27 R</b>" in messages[1]
    assert "Entrada 1.40710 → salida 1.41330 (+0.44 %)" in messages[1] and "Duración: 12 h 0 min" in messages[1]
    assert pending_alerts([bot([OPEN], [CLOSED])], [], state, NOW)[0] == []


def test_new_errors_are_grouped_in_one_message():
    older = {**ERROR, "logged_at": "2026-11-09T06:30:00"}
    [message], state = pending_alerts([bot(events=[ERROR, older])], [], AlertState(), NOW)
    assert "2 errores" in message and "06:36 BTC/USD" in message and "Connection aborted" in message
    assert pending_alerts([bot(events=[ERROR, older])], [], state, NOW)[0] == []


def test_outside_text_is_escaped_for_telegram_html():
    bad = {**ERROR, "detail": {"message": "status <500> & retry"}}
    [message], _ = pending_alerts([bot(events=[bad])], [], AlertState(), NOW)
    assert "status &lt;500&gt; &amp; retry" in message


def test_silent_bot_is_alerted_once_and_again_when_it_comes_back():
    silent = bot(last_beat=NOW - timedelta(minutes=30))
    [message], state = pending_alerts([silent], [], AlertState(), NOW)
    assert "Bot caído" in message and "09/11 18:35" in message
    assert pending_alerts([silent], [], state, NOW)[0] == []
    [message], state = pending_alerts([bot()], [], state, NOW)
    assert "Bot de vuelta" in message and state.down == set()


def test_liveness_is_not_judged_while_the_watcher_starts():
    silent = bot(last_beat=NOW - timedelta(hours=8))
    assert pending_alerts([silent], [], AlertState(), NOW, check_liveness=False) == ([], AlertState())


def test_broker_down_and_back():
    [message], state = pending_alerts([], [ALPACA_DOWN], AlertState(), NOW)
    assert "Broker sin respuesta" in message and "Read timed out" in message
    assert pending_alerts([], [ALPACA_DOWN], state, NOW)[0] == []
    [message], state = pending_alerts([], [ALPACA_OK], state, NOW)
    assert "Broker de vuelta" in message and state.brokers_down == set()


def test_first_run_records_without_sending_and_reads_the_old_format(tmp_path, monkeypatch):
    sent_messages, path = [], tmp_path / "sent.json"
    monkeypatch.setattr("mt5bot.main.ALERTS_PATH", path)
    monkeypatch.setattr("mt5bot.io.telegram.send", lambda token, chat, text: sent_messages.append(text))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    notify([bot(trades=[CLOSED], events=[ERROR])], [], check_liveness=False)  # el latido se prueba aparte
    assert sent_messages == []                        # lo que ya había no se avisa
    path.write_text(json.dumps(["260514-close-5"]))   # formato anterior: lista de operaciones avisadas
    notify([bot([OPEN], [CLOSED])], [], check_liveness=False)  # el latido se prueba aparte
    assert len(sent_messages) == 1 and "BTC/USD" in sent_messages[0]
