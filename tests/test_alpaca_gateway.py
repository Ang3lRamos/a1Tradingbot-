"""El conector de Alpaca contra clientes falsos: sin red ni llaves."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("alpaca")

from mt5bot.core.models import OrderPlan, Signal  # noqa: E402
from mt5bot.io.alpaca_gateway import AlpacaGateway  # noqa: E402
from mt5bot.report import closed_trades  # noqa: E402

MAGIC = 260513
CALENDAR = [SimpleNamespace(date=datetime(2026, 11, d).date(), open=datetime(2026, 11, d, 9, 30),
                            close=datetime(2026, 11, d, 16, 0)) for d in (4, 5, 6, 9)]
FILLED_AT = datetime(2026, 11, 5, 14, 31, tzinfo=timezone.utc)  # 09:31 en Nueva York


def order(id, client_id, status="filled", side="buy", type="market", qty=10, price=None, legs=None, **extra):
    return SimpleNamespace(id=id, client_order_id=client_id, symbol="SPY", status=status, side=side, type=type,
                           filled_qty=qty if status == "filled" else 0, filled_avg_price=price,
                           filled_at=FILLED_AT if status == "filled" else None, legs=legs or [], **extra)


def bracket(ticket=1, stop_status="new", target_status="new", qty=10):
    legs = [order("stop-leg", "x", status=stop_status, side="sell", type="stop", qty=qty, price=560.0, stop_price="560.0"),
            order("tp-leg", "y", status=target_status, side="sell", type="limit", qty=qty, limit_price="700.0")]
    return order("entry", f"{MAGIC}-open-{ticket}", qty=qty, price=600.0, legs=legs)


def fractional(ticket=1, stops=(("stop-1", "new", "560.0"),), qty=0.5):
    """Entrada fraccionada sin bracket y sus stops DAY aparte (id, estado, precio)."""
    entry = order("entry", f"{MAGIC}-open-{ticket}", qty=qty, price=600.0)
    return [entry, *(order(id, f"{MAGIC}-stop-{ticket}-{n}", status=status, side="sell", type="stop", qty=qty,
                           stop_price=price) for n, (id, status, price) in enumerate(stops))]


class FakeTrading:
    def __init__(self, orders=(), held=(), equity=100_500.0, last_equity=100_000.0, fractionable=True):
        self.orders, self.held, self.equity, self.last_equity = list(orders), list(held), equity, last_equity
        self.fractionable = fractionable
        self.submitted, self.cancelled = [], []

    def get_account(self):
        return SimpleNamespace(equity=str(self.equity), last_equity=str(self.last_equity), trading_blocked=False,
                               account_blocked=False, account_number="PA123")

    def get_asset(self, symbol):
        return SimpleNamespace(tradable=True, fractionable=self.fractionable)

    def get_all_positions(self):
        return self.held

    def get_orders(self, request):
        return self.orders

    def get_calendar(self, request):
        return CALENDAR

    def get_order_by_id(self, order_id):
        if order_id == "submitted":
            return order("submitted", "z", price=601.25)
        return next(o for o in [*self.orders, *[leg for o in self.orders for leg in o.legs]] if o.id == order_id)

    def cancel_order_by_id(self, order_id):
        self.cancelled.append(order_id)
        for leg in (leg for o in self.orders for leg in o.legs):
            leg.status = "canceled"  # OCO: cancelar una pata cancela la otra
        for o in self.orders:
            if o.id == order_id:
                o.status = "canceled"

    def submit_order(self, request):
        self.submitted.append(request)
        return SimpleNamespace(id="submitted")


class FakeData:
    def get_stock_bars(self, request):
        # Velas diarias de Alpaca: marca de tiempo a medianoche de Nueva York (05:00 UTC en invierno).
        bars = [SimpleNamespace(timestamp=datetime(2026, 11, d, 5, tzinfo=timezone.utc), open=d, high=d + 1,
                                low=d - 1, close=d + 0.5, volume=1000) for d in (2, 3, 4, 5, 6, 9)]
        return SimpleNamespace(data={"SPY": bars})

    def get_stock_latest_quote(self, request):
        return {"SPY": SimpleNamespace(bid_price=600.0, ask_price=600.02)}


def gateway(trading=None, now=datetime(2026, 11, 9, 8, 0), fractional=False):
    return AlpacaGateway(trading or FakeTrading(), FakeData(), paper=True, now=lambda: now, fractional=fractional)


def held(qty="10", unrealized="50"):
    return SimpleNamespace(symbol="SPY", qty=qty, avg_entry_price="600.0", unrealized_pl=unrealized)


def test_daily_bar_closes_when_the_next_session_opens():
    before_open = gateway(now=datetime(2026, 11, 9, 8, 0))
    assert before_open.closed_bars("SPY", "D1", 10)["time"].iloc[-1] == datetime(2026, 11, 5)
    assert before_open.forming_bar_time("SPY", "D1") == datetime(2026, 11, 6, 9, 30)
    after_open = gateway(now=datetime(2026, 11, 9, 9, 31))
    assert after_open.closed_bars("SPY", "D1", 10)["time"].iloc[-1] == datetime(2026, 11, 6)
    assert after_open.forming_bar_time("SPY", "D1") == datetime(2026, 11, 9, 9, 30)


def test_only_daily_bars_are_supported():
    with pytest.raises(Exception, match="D1"):
        gateway().closed_bars("SPY", "H4", 10)


def test_bot_position_reads_stop_and_target_from_bracket():
    [position] = gateway(FakeTrading([bracket()], [held()])).positions(MAGIC, "SPY")
    assert (position.ticket, position.volume, position.sl, position.tp) == (1, 10.0, 560.0, 700.0)
    assert position.is_buy and position.stop_leg_id == "stop-leg" and not position.closing


def test_manual_or_closed_positions_are_not_the_bots():
    assert gateway(FakeTrading([bracket()], [held(qty="15")])).positions(MAGIC) == []        # cantidad distinta
    assert gateway(FakeTrading([bracket(stop_status="filled")], [held()])).positions(MAGIC) == []  # salió por SL
    assert gateway(FakeTrading([], [held()])).positions(MAGIC) == []                          # sin orden del bot
    other_bot = order("entry", "999-open-1", qty=10, price=600.0)
    assert gateway(FakeTrading([other_bot], [held()])).positions(MAGIC) == []


def test_close_cancels_bracket_legs_before_selling():
    trading = FakeTrading([bracket()], [held()])
    gate = gateway(trading)
    [position] = gate.positions(MAGIC)
    gate.close_position(position, "regla de salida")
    assert trading.cancelled == ["stop-leg"]
    [sell] = trading.submitted
    assert sell.side.value == "sell" and sell.qty == 10 and sell.client_order_id.startswith(f"{MAGIC}-close-1-")


def test_close_is_not_sent_twice_while_one_is_queued():
    queued = order("close", f"{MAGIC}-close-1-5", status="accepted", side="sell")
    trading = FakeTrading([bracket(stop_status="canceled", target_status="canceled"), queued], [held()])
    [position] = gateway(trading).positions(MAGIC)
    assert position.closing and gateway(trading).close_position(position, "kill switch") is None
    assert trading.submitted == []


def test_market_order_carries_stop_and_target_on_the_server():
    trading = FakeTrading()
    signal = Signal("SPY", "buy", datetime(2026, 11, 6), 600.004, 560.123, 840.456, "test")
    result = gateway(trading).send_market_order(OrderPlan(signal, 12.0, 480.0), MAGIC, "rsi2 buy")
    [sent] = trading.submitted
    assert sent.order_class.value == "bracket" and sent.time_in_force.value == "gtc" and sent.qty == 12
    assert sent.stop_loss.stop_price == 560.12 and sent.take_profit.limit_price == 840.46
    assert sent.client_order_id == f"{MAGIC}-open-{result.order}" and result.price == 601.25


def test_closed_trade_from_stop_leg_has_pnl_and_r():
    trading = FakeTrading([bracket(stop_status="filled", target_status="canceled")])
    trade = closed_trades(gateway(trading).bot_deals(MAGIC, datetime(2026, 1, 1)), {1: {"risk_money": 400.0}})[0]
    assert trade["pnl"] == pytest.approx(-400.0) and trade["r"] == pytest.approx(-1.0)


def test_daily_pnl_includes_floating():
    gate = gateway(FakeTrading([bracket()], [held(unrealized="50")], equity=100_500.0, last_equity=100_000.0))
    balance, equity = gate.balance_and_equity()
    realized, entries = gate.today_deals(MAGIC, datetime(2026, 11, 5, 10, 0))
    assert equity - (balance - realized) == pytest.approx(500.0)   # lo que el motor usa como pnl_today
    assert entries == 1


def test_whole_shares_and_spread_in_cents():
    gate = gateway()
    spec = gate.symbol_spec("SPY")
    assert (spec.volume_min, spec.volume_step, spec.tick_value) == (1, 1, 0.01)   # 1 lote = 1 acción
    _, bid, ask = gate.quote("SPY")
    assert round((ask - bid) / spec.point) == 2


def test_alpaca_config_loads_in_dry_run():
    from pathlib import Path

    from mt5bot.config import load_settings
    settings = load_settings(Path(__file__).parents[1] / "config" / "alpaca_rsi2.toml")
    assert settings.bot.broker == "alpaca" and settings.bot.mode == "dry_run" and not settings.bot.allow_real_account


def test_fractional_spec_allows_fractions_only_on_fractionable_assets():
    spec = gateway(fractional=True).symbol_spec("SPY")
    assert (spec.volume_min, spec.volume_step) == (0.0001, 0.0001)
    with pytest.raises(Exception, match="fraccionadas"):
        gateway(FakeTrading(fractionable=False), fractional=True).symbol_spec("SPY")


def test_fractional_entry_is_a_day_market_order_followed_by_a_day_stop():
    trading = FakeTrading()
    signal = Signal("SPY", "buy", datetime(2026, 11, 6), 600.0, 560.123, 840.0, "test")
    result = gateway(trading, fractional=True).send_market_order(OrderPlan(signal, 0.12341, 4.8), MAGIC, "rsi2 buy")
    entry, stop = trading.submitted
    assert entry.qty == 0.1234 and entry.time_in_force.value == "day" and entry.order_class is None
    assert entry.take_profit is None and entry.client_order_id == f"{MAGIC}-open-{result.order}"
    assert stop.type.value == "stop" and stop.time_in_force.value == "day" and stop.side.value == "sell"
    assert stop.stop_price == 560.12 and stop.qty == 10      # la cantidad que se llenó
    assert stop.client_order_id.startswith(f"{MAGIC}-stop-{result.order}-")


def test_fractional_short_is_refused():
    signal = Signal("SPY", "sell", datetime(2026, 11, 6), 600.0, 640.0, 400.0, "test")
    with pytest.raises(Exception, match="corto"):
        gateway(fractional=True).send_market_order(OrderPlan(signal, 0.1, 4.0), MAGIC, "rsi2 sell")


def test_fractional_position_reads_its_day_stop():
    gate = gateway(FakeTrading(fractional(), [held(qty="0.5")]))
    [position] = gate.positions(MAGIC, "SPY")
    assert (position.volume, position.sl, position.tp, position.stop_leg_id) == (0.5, 560.0, None, "stop-1")
    assert not position.bracket and gate.positions_without_stop(MAGIC, "SPY") == []


def test_expired_day_stop_is_reported_with_its_latest_price():
    stops = (("stop-1", "expired", "550.0"), ("stop-2", "expired", "560.0"))
    gate = gateway(FakeTrading(fractional(stops=stops), [held(qty="0.5")]))
    [position] = gate.positions_without_stop(MAGIC, "SPY")
    assert position.sl == 560.0 and position.stop_leg_id is None   # el más ajustado: solo se mueve a favor


def test_bracket_and_closing_positions_need_no_new_stop():
    assert gateway(FakeTrading([bracket(stop_status="canceled", target_status="canceled")],
                               [held()])).positions_without_stop(MAGIC, "SPY") == []
    queued = order("close", f"{MAGIC}-close-1-5", status="accepted", side="sell")
    expired = fractional(stops=(("stop-1", "expired", "560.0"),))
    assert gateway(FakeTrading([*expired, queued], [held(qty="0.5")])).positions_without_stop(MAGIC, "SPY") == []


def test_filled_day_stop_closes_the_fractional_position():
    gate = gateway(FakeTrading(fractional(stops=(("stop-1", "filled", "560.0"),)), [held(qty="0.5")]))
    assert gate.positions(MAGIC) == []


def test_fractional_close_cancels_the_stop_before_selling():
    trading = FakeTrading(fractional(), [held(qty="0.5")])
    gate = gateway(trading, fractional=True)
    [position] = gate.positions(MAGIC)
    gate.close_position(position, "regla de salida")
    assert trading.cancelled == ["stop-1"]
    [sell] = trading.submitted
    assert sell.side.value == "sell" and sell.qty == 0.5 and sell.client_order_id.startswith(f"{MAGIC}-close-1-")


def test_renewed_stop_uses_position_quantity():
    trading = FakeTrading(fractional(stops=(("stop-1", "expired", "560.0"),)), [held(qty="0.5")])
    gate = gateway(trading, fractional=True)
    [position] = gate.positions_without_stop(MAGIC, "SPY")
    gate.place_stop(position, position.sl)
    [stop] = trading.submitted
    assert (stop.qty, stop.stop_price, stop.time_in_force.value) == (0.5, 560.0, "day")
