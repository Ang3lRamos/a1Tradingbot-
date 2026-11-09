"""El conector de cripto de Alpaca contra clientes falsos: sin red ni llaves."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("alpaca")

from mt5bot.config import load_settings  # noqa: E402
from mt5bot.core.models import OrderPlan, Signal  # noqa: E402
from mt5bot.io.alpaca_crypto import AlpacaCryptoGateway  # noqa: E402
from tests.test_alpaca_gateway import FakeTrading, order  # noqa: E402

MAGIC = 260514
BOUGHT, HELD = 0.0001, 0.00009975   # la comisión de compra (0.25 %) se cobra en BTC


def crypto_order(id, client_id, **fields):
    entry = order(id, client_id, **fields)
    entry.symbol = "BTC/USD"
    return entry


class FakeCryptoTrading(FakeTrading):
    def get_asset(self, symbol):
        return SimpleNamespace(tradable=True, fractionable=True, min_order_size="0.000013299")

    def get_open_position(self, symbol):
        return next(p for p in self.held if p.symbol == symbol)


class FakeCryptoData:
    def get_crypto_bars(self, request):
        # Velas diarias de cripto: empiezan a medianoche UTC (19:00 en Nueva York en invierno).
        bars = [SimpleNamespace(timestamp=datetime(2026, 11, d, tzinfo=timezone.utc), open=d, high=d + 1, low=d - 1,
                                close=d + 0.5, volume=10) for d in range(1, 10)]
        return SimpleNamespace(data={"BTC/USD": bars})

    def get_crypto_latest_quote(self, request):
        return {"BTC/USD": SimpleNamespace(bid_price=74_894.9, ask_price=74_914.07)}


def gateway(trading=None, now=datetime(2026, 11, 8, 18, 0)):
    return AlpacaCryptoGateway(trading or FakeCryptoTrading(), FakeCryptoData(), paper=True, now=lambda: now)


def held(qty=HELD):
    return SimpleNamespace(symbol="BTCUSD", qty=str(qty), avg_entry_price="75000.0", unrealized_pl="0.1")


def open_position(stop_status="new"):
    entry = crypto_order("entry", f"{MAGIC}-open-1", qty=BOUGHT, price=75_000.0)
    stop = crypto_order("stop-1", f"{MAGIC}-stop-1-1", status=stop_status, side="sell", type="stop_limit",
                        qty=HELD, stop_price="68000.0")
    return FakeCryptoTrading([entry, stop], [held()])


def test_daily_bar_closes_at_midnight_utc():
    before = gateway(now=datetime(2026, 11, 8, 18, 59))
    assert before.forming_bar_time("BTC/USD", "D1") == datetime(2026, 11, 7, 19, 0)
    assert before.closed_bars("BTC/USD", "D1", 5)["time"].iloc[-1] == datetime(2026, 11, 6, 19, 0)
    after = gateway(now=datetime(2026, 11, 8, 19, 1))
    assert after.forming_bar_time("BTC/USD", "D1") == datetime(2026, 11, 8, 19, 0)
    bars = after.closed_bars("BTC/USD", "D1", 5)
    assert bars["time"].iloc[-1] == datetime(2026, 11, 7, 19, 0) and len(bars) == 5
    assert (bars["time"].diff().dropna() == timedelta(days=1)).all()   # incluye sábado y domingo


def test_spec_uses_the_minimum_order_of_the_asset():
    spec = gateway().symbol_spec("BTC/USD")
    assert (spec.volume_min, spec.volume_step, spec.tick_value) == (0.000013299, 1e-8, 0.01)
    _, bid, ask = gateway().quote("BTC/USD")
    assert round((ask - bid) / spec.point) == 1917


def test_entry_is_gtc_market_then_server_stop_limit_on_the_held_quantity():
    trading = FakeCryptoTrading(held=[held()])
    signal = Signal("BTC/USD", "buy", datetime(2026, 11, 7, 19), 75_000.0, 68_000.123, 117_000.0, "test")
    result = gateway(trading).send_market_order(OrderPlan(signal, BOUGHT, 0.7), MAGIC, "rsi2 buy")
    entry, stop = trading.submitted
    assert entry.qty == BOUGHT and entry.time_in_force.value == "gtc" and entry.order_class is None
    assert entry.client_order_id == f"{MAGIC}-open-{result.order}"
    assert stop.type.value == "stop_limit" and stop.time_in_force.value == "gtc" and stop.side.value == "sell"
    assert (stop.qty, stop.stop_price, stop.limit_price) == (HELD, 68_000.12, 66_640.12)


def test_short_is_refused():
    signal = Signal("BTC/USD", "sell", datetime(2026, 11, 7, 19), 75_000.0, 80_000.0, 40_000.0, "test")
    with pytest.raises(Exception, match="corto"):
        gateway().send_market_order(OrderPlan(signal, BOUGHT, 0.5), MAGIC, "rsi2 sell")


def test_position_matches_despite_symbol_format_and_fee():
    [position] = gateway(open_position()).positions(MAGIC, "BTC/USD")
    assert (position.volume, position.sl, position.stop_leg_id) == (HELD, 68_000.0, "stop-1")
    assert gateway(FakeCryptoTrading(open_position().orders, [held(qty=0.00005)])).positions(MAGIC) == []  # otra cantidad


def test_cancelled_stop_is_renewed_and_close_is_gtc():
    trading = open_position(stop_status="canceled")
    gate = gateway(trading)
    [position] = gate.positions_without_stop(MAGIC, "BTC/USD")
    gate.place_stop(position, position.sl)
    gate.close_position(position, "regla de salida")
    stop, close = trading.submitted
    assert (stop.type.value, stop.qty, stop.stop_price) == ("stop_limit", HELD, 68_000.0)
    assert close.time_in_force.value == "gtc" and close.qty == HELD


def test_crypto_config_loads_in_dry_run_with_weekends():
    settings = load_settings(Path(__file__).parents[1] / "config" / "alpaca_crypto.toml")
    assert settings.bot.broker == "alpaca_crypto" and settings.bot.mode == "dry_run"
    assert settings.strategy.rsi2.weekends and not settings.bot.allow_real_account
