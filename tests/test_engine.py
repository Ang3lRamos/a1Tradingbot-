"""El ciclo del bot contra un MT5 falso: sin Windows ni terminal."""
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from mt5bot.engine import Bot
from mt5bot.io.journal import Journal
from mt5bot.io.mt5_gateway import Mt5Error
from tests.conftest import make_bars, range_rows

BARS = make_bars("2026-11-02", range_rows() + [("09:00", 1.1005, 1.1016, 1.1005, 1.1015)])
JUST_AFTER_CLOSE = datetime(2026, 11, 2, 9, 15, 2)


class FakeGateway:
    def __init__(self, spec, demo=True, open_positions=(), now=JUST_AFTER_CLOSE):
        self.spec, self.demo, self.now = spec, demo, now
        self.open_positions = list(open_positions)
        self.sent, self.closed, self.modified = [], [], []

    def is_demo_account(self):
        return self.demo

    def quote(self, symbol):
        return self.now, 1.10160, 1.10168

    def closed_bars(self, symbol, timeframe, count):
        return BARS

    def forming_bar_time(self, symbol, timeframe):
        return getattr(self, "forming", BARS["time"].iloc[-1].to_pydatetime() + timedelta(minutes=15))

    def positions(self, magic, symbol=None):
        return self.open_positions

    def position_is_buy(self, position):
        return position.type == "buy"

    def symbol_spec(self, symbol):
        return self.spec

    def balance_and_equity(self):
        return 1000.0, 1000.0

    def today_deals(self, magic, server_now):
        return 0.0, 0

    def send_market_order(self, plan, magic, comment):
        self.sent.append(plan)
        return SimpleNamespace(order=42, price=plan.signal.entry)

    def modify_stop(self, position, new_stop):
        self.modified.append((position.ticket, new_stop))

    def close_position(self, position, comment):
        self.closed.append((position.ticket, comment))


def kinds(journal):
    return [row[0] for row in journal.db.execute("SELECT kind FROM events ORDER BY id")]


@pytest.fixture
def journal(tmp_path):
    j = Journal(tmp_path / "journal.db")
    yield j
    j.close()


def live(settings):
    return replace(settings, bot=replace(settings.bot, mode="live"))


def open_buy(journal, ticket=7, entry=1.1005, stop=1.0995):
    plan = SimpleNamespace(signal=SimpleNamespace(symbol="EURUSD", side="buy", entry=entry, stop=stop, target=1.1035),
                           lots=0.05, risk_money=5.0)
    journal.record_position(ticket, plan, datetime(2026, 11, 2, 8, 0))
    return SimpleNamespace(ticket=ticket, symbol="EURUSD", type="buy", price_open=entry, sl=stop, tp=1.1035)


def test_dry_run_logs_but_sends_nothing(orb_settings, eurusd, journal):
    gateway = FakeGateway(eurusd)
    Bot(gateway, orb_settings, journal).run_cycle("EURUSD")
    assert kinds(journal) == ["signal", "dry_run"]
    assert gateway.sent == []


def test_live_sends_order_and_records_initial_stop(orb_settings, eurusd, journal):
    gateway = FakeGateway(eurusd)
    Bot(gateway, live(orb_settings), journal).run_cycle("EURUSD")
    assert kinds(journal) == ["signal", "order_sent"]
    plan = gateway.sent[0]
    assert plan.signal.entry == 1.10168  # compra al ask
    assert plan.risk_money <= 5.0        # 0.5% de 1000
    assert journal.initial_stop(42) == pytest.approx(1.1005)


def test_same_bar_is_not_traded_twice(orb_settings, eurusd, journal):
    gateway = FakeGateway(eurusd)
    bot = Bot(gateway, live(orb_settings), journal)
    bot.run_cycle("EURUSD")
    bot.run_cycle("EURUSD")
    assert len(gateway.sent) == 1


def test_stale_signal_at_startup_is_skipped(orb_settings, eurusd, journal):
    # La vela de las 09:00 cierra a las 09:15; a las 09:21 ya pasaron más de 5 minutos.
    gateway = FakeGateway(eurusd, now=datetime(2026, 11, 2, 9, 21))
    Bot(gateway, live(orb_settings), journal).run_cycle("EURUSD")
    assert gateway.sent == []
    assert kinds(journal) == ["skipped"]


def test_breakeven_moves_stop_on_new_bar(orb_settings, eurusd, journal):
    position = open_buy(journal)  # bid 1.1016 = +1.1R
    gateway = FakeGateway(eurusd, open_positions=[position])
    Bot(gateway, orb_settings, journal).run_cycle("EURUSD")
    assert gateway.modified == [(7, 1.1005)]


def test_positions_are_closed_before_the_weekend(orb_settings, eurusd, journal):
    position = open_buy(journal)
    gateway = FakeGateway(eurusd, open_positions=[position], now=datetime(2026, 11, 6, 20, 1))
    Bot(gateway, orb_settings, journal).run_cycle("EURUSD")
    assert gateway.closed == [(7, "weekend")]


def test_live_on_real_account_is_refused(orb_settings, eurusd, journal):
    with pytest.raises(Mt5Error):
        Bot(FakeGateway(eurusd, demo=False), live(orb_settings), journal).check_account_allowed()


def test_kill_switch_closes_positions(settings, eurusd, journal, tmp_path):
    stop_file = tmp_path / "STOP"
    stop_file.touch()
    position = SimpleNamespace(ticket=7, symbol="EURUSD")
    gateway = FakeGateway(eurusd, open_positions=[position])
    cfg = replace(settings, bot=replace(settings.bot, kill_switch_file=stop_file))
    Bot(gateway, cfg, journal).run_forever()
    assert gateway.closed == [(7, "kill switch")]
