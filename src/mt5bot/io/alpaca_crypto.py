"""Cripto al contado en Alpaca (BTC/USD, ETH/USD...): mismo conector que los ETF con las diferencias de cripto.

- Mercado 24/7. La vela diaria de Alpaca empieza a medianoche UTC; como en el resto del conector, la "hora del
  servidor" es la de Nueva York sin huso, así que la vela abre a las 19:00 (20:00 con horario de verano).
- Sin cortos y sin bracket: la entrada es una orden a mercado GTC y el stop una orden stop-limit GTC aparte
  "<magic>-stop-<ticket>-<n>" que vive en el servidor (Alpaca no acepta stop simple en cripto). El límite queda
  STOP_LIMIT_SLIPPAGE por debajo del stop: si el precio salta más que eso, la orden no se llena y el motor no lo ve
  como stop vencido (sigue activa). Si el stop falta, el motor lo repone (positions_without_stop / place_stop).
- La comisión de compra se cobra en la moneda recibida: la posición queda un poco menor que lo comprado. Por eso el
  stop y el cierre usan la cantidad de la posición y no la de la orden.
"""
import time as clock
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
from alpaca.data.requests import CryptoBarsRequest, CryptoLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, ReplaceOrderRequest, StopLimitOrderRequest

from mt5bot.core.models import OrderPlan, SymbolSpec
from mt5bot.io.alpaca_gateway import NEW_YORK, AlpacaError, AlpacaGateway, _filled, _new_york

CRYPTO_STEP = 1e-8          # Alpaca acepta 9 decimales; el cálculo de lotes redondea a 8
STOP_LIMIT_SLIPPAGE = 0.02  # el límite del stop queda 2 % por debajo: margen para velas bruscas sin vender regalado
FEE_TOLERANCE = 0.01        # la comisión (0.25 % en nivel 1) achica la posición respecto a la orden de compra


def _price(value: float) -> float:
    return round(value, 2 if value >= 1 else 6)


class AlpacaCryptoGateway(AlpacaGateway):
    close_time_in_force = TimeInForce.GTC  # cripto no admite órdenes DAY

    @classmethod
    def from_keys(cls, api_key: str, secret_key: str, paper: bool, fractional: bool = False) -> "AlpacaCryptoGateway":
        from alpaca.data.historical import CryptoHistoricalDataClient
        from alpaca.trading.client import TradingClient
        return cls(TradingClient(api_key, secret_key, paper=paper), CryptoHistoricalDataClient(api_key, secret_key),
                   paper)

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        asset = self._call(self.trading.get_asset, symbol)
        if not asset.tradable:
            raise AlpacaError(f"{symbol} no se puede operar en Alpaca")
        return SymbolSpec(name=symbol, digits=2, point=0.01, tick_size=0.01, tick_value=0.01,
                          volume_min=max(float(asset.min_order_size), CRYPTO_STEP), volume_max=1e9,
                          volume_step=CRYPTO_STEP)

    def closed_bars(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        forming = self._forming_day()
        bars = self._crypto_bars(symbol, timeframe, (forming - timedelta(days=count + 5)).date())
        bars = bars[bars["time"] < pd.Timestamp(forming)]
        if bars.empty:
            raise AlpacaError(f"sin velas cerradas para {symbol}")
        return bars.tail(count).reset_index(drop=True)

    def forming_bar_time(self, symbol: str, timeframe: str) -> datetime:
        return self._forming_day()

    def bars_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        bars = self._crypto_bars(symbol, timeframe, start.date())
        keep = (bars["time"] < pd.Timestamp(self._forming_day())) & (bars["time"] <= pd.Timestamp(end))
        return bars[keep].reset_index(drop=True)

    def quote(self, symbol: str) -> tuple[datetime, float, float]:
        request = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
        last = self._call(self.data.get_crypto_latest_quote, request)[symbol]
        return self._now(), float(last.bid_price), float(last.ask_price)

    def send_market_order(self, plan: OrderPlan, magic: int, comment: str):
        signal, ticket = plan.signal, int(clock.time() * 1000)
        if signal.side != "buy":
            raise AlpacaError(f"{signal.symbol}: Alpaca no admite ventas en corto de cripto")
        request = MarketOrderRequest(
            symbol=signal.symbol, qty=round(plan.lots, 9), side=OrderSide.BUY, type=OrderType.MARKET,
            time_in_force=TimeInForce.GTC, client_order_id=f"{magic}-open-{ticket}",
        )
        order = self._wait(self._call(self.trading.submit_order, request).id, _filled)
        if _filled(order):
            held = self._call(self.trading.get_open_position, signal.symbol.replace("/", ""))
            self._submit_stop(signal.symbol, abs(float(held.qty)), True, signal.stop, magic, ticket)
        # Si aún no se llenó, el motor pone el stop en la vuelta siguiente (positions_without_stop).
        price = float(order.filled_avg_price) if order.filled_avg_price else None
        return SimpleNamespace(order=ticket, price=price)

    def _submit_stop(self, symbol: str, qty: float, is_buy: bool, stop: float, magic: int, ticket: int):
        request = StopLimitOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.SELL, type=OrderType.STOP_LIMIT, time_in_force=TimeInForce.GTC,
            stop_price=_price(stop), limit_price=_price(stop * (1 - STOP_LIMIT_SLIPPAGE)),
            client_order_id=f"{magic}-stop-{ticket}-{int(clock.time() * 1000)}",
        )
        return self._call(self.trading.submit_order, request)

    def modify_stop(self, position, new_stop: float):
        if position.stop_leg_id is None:
            raise AlpacaError(f"{position.symbol}: la posición {position.ticket} no tiene orden de stop")
        request = ReplaceOrderRequest(stop_price=_price(new_stop),
                                      limit_price=_price(new_stop * (1 - STOP_LIMIT_SLIPPAGE)))
        return self._call(self.trading.replace_order_by_id, position.stop_leg_id, request)

    @staticmethod
    def _same_size(held_qty: float, filled_qty: float) -> bool:
        return filled_qty * (1 - FEE_TOLERANCE) <= held_qty <= filled_qty

    def _forming_day(self) -> datetime:
        """Inicio de la vela diaria en formación (medianoche UTC) en hora de Nueva York."""
        now_utc = self._now().replace(tzinfo=NEW_YORK).astimezone(timezone.utc)
        return _new_york(now_utc.replace(hour=0, minute=0, second=0, microsecond=0))

    def _crypto_bars(self, symbol: str, timeframe: str, start: date) -> pd.DataFrame:
        if timeframe != "D1":
            raise AlpacaError(f"el conector de Alpaca solo maneja velas D1, no {timeframe}")
        request = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
                                    start=datetime.combine(start, datetime.min.time(), timezone.utc))
        found = self._call(self.data.get_crypto_bars, request).data.get(symbol, [])
        bars = pd.DataFrame([{
            "time": _new_york(b.timestamp), "open": b.open, "high": b.high, "low": b.low, "close": b.close,
            "tick_volume": b.volume, "spread": 0,
        } for b in found], columns=["time", "open", "high", "low", "close", "tick_volume", "spread"])
        bars["time"] = pd.to_datetime(bars["time"])
        return bars
