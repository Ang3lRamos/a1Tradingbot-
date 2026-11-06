"""Conector con Alpaca (acciones y ETF de EE. UU.) con la misma interfaz que Mt5Gateway: el motor no cambia.

Diferencias con MT5 que importan:
- La "hora del servidor" es la de Nueva York, sin huso (igual que MT5 entrega la suya).
- Una vela diaria se da por cerrada cuando abre la sesión siguiente, como en MT5 (la posición 0 es la que se forma).
  Así la señal se evalúa a las 09:30 y la orden entra a la apertura, que es lo que supone el backtest.
- Alpaca no tiene magic: las órdenes del bot llevan client_order_id "<magic>-open-<ticket>" y
  "<magic>-close-<ticket>-<n>". Una posición es del bot si su última entrada sigue sin salida y coincide en cantidad.
- 1 lote = 1 acción entera: las órdenes bracket (SL y TP en el servidor) no admiten fraccionadas.
"""
import time as clock
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.enums import OrderClass, OrderSide, OrderType, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (GetCalendarRequest, GetOrdersRequest, MarketOrderRequest, ReplaceOrderRequest,
                                     StopLossRequest, TakeProfitRequest)
from requests.exceptions import RequestException

from mt5bot.core.models import OrderPlan, SymbolSpec
from mt5bot.io.mt5_gateway import Mt5Error

NEW_YORK = ZoneInfo("America/New_York")
SIP_DELAY = timedelta(minutes=16)  # el plan gratuito da datos SIP (todas las bolsas) con 15 minutos de atraso
MAX_SHARES = 100_000
MAX_ORDERS = 500
WAIT_SECONDS = 15
FINISHED = {"filled", "canceled", "expired", "rejected", "replaced", "done_for_day"}


class AlpacaError(Mt5Error):
    """Subclase de Mt5Error para que el motor la trate igual: la anota y sigue con el siguiente símbolo."""


@dataclass(frozen=True)
class BrokerPosition:
    """Lo que el motor y el panel leen de una posición de MT5, armado desde las órdenes de Alpaca."""
    ticket: int
    symbol: str
    volume: float
    price_open: float
    sl: float | None
    tp: float | None
    profit: float
    magic: int
    is_buy: bool
    stop_leg_id: str | None
    open_leg_ids: tuple[str, ...]
    closing: bool  # ya hay una orden de cierre del bot en cola (p. ej. enviada fuera de horario)
    swap: float = 0.0


def _value(field) -> str:
    return getattr(field, "value", field)


def _new_york(moment: datetime) -> datetime:
    return moment.astimezone(NEW_YORK).replace(tzinfo=None) if moment.tzinfo else moment


def _parse_id(client_order_id: str, magic: int) -> tuple[str, int] | None:
    parts = (client_order_id or "").split("-")
    if len(parts) >= 3 and parts[0] == str(magic) and parts[1] in ("open", "close") and parts[2].isdigit():
        return parts[1], int(parts[2])
    return None


def _filled(order) -> bool:
    return _value(order.status) == "filled"


class AlpacaGateway:
    def __init__(self, trading, data, paper: bool, now=None):
        self.trading, self.data, self.paper = trading, data, paper
        self._now = now or (lambda: datetime.now(NEW_YORK).replace(tzinfo=None))
        self._calendar: tuple[date, list] | None = None

    @classmethod
    def from_keys(cls, api_key: str, secret_key: str, paper: bool) -> "AlpacaGateway":
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.trading.client import TradingClient
        return cls(TradingClient(api_key, secret_key, paper=paper), StockHistoricalDataClient(api_key, secret_key), paper)

    def connect(self) -> None:
        account = self._call(self.trading.get_account)
        if account.trading_blocked or account.account_blocked:
            raise AlpacaError(f"la cuenta de Alpaca {account.account_number} tiene el trading bloqueado")

    def shutdown(self) -> None:
        pass

    def is_demo_account(self) -> bool:
        return self.paper

    def balance_and_equity(self) -> tuple[float, float]:
        # Como en MT5: balance = lo cerrado, equity = balance + flotante.
        equity = float(self._call(self.trading.get_account).equity)
        unrealized = sum(float(p.unrealized_pl or 0) for p in self._call(self.trading.get_all_positions))
        return equity - unrealized, equity

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        asset = self._call(self.trading.get_asset, symbol)
        if not asset.tradable:
            raise AlpacaError(f"{symbol} no se puede operar en Alpaca")
        return SymbolSpec(name=symbol, digits=2, point=0.01, tick_size=0.01, tick_value=0.01,
                          volume_min=1, volume_max=MAX_SHARES, volume_step=1)

    def closed_bars(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        session_day, _ = self._forming_session()
        bars = self._daily_bars(symbol, timeframe, session_day - timedelta(days=int(count * 1.5) + 10))
        bars = bars[bars["time"] < pd.Timestamp(session_day)]
        if bars.empty:
            raise AlpacaError(f"sin velas cerradas para {symbol}")
        return bars.tail(count).reset_index(drop=True)

    def forming_bar_time(self, symbol: str, timeframe: str) -> datetime:
        """Apertura de la última sesión que ya empezó: es la 'vela en formación' de MT5."""
        return self._forming_session()[1]

    def bars_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        session_day, _ = self._forming_session()
        bars = self._daily_bars(symbol, timeframe, start.date())
        return bars[(bars["time"] < pd.Timestamp(session_day)) & (bars["time"] <= pd.Timestamp(end))].reset_index(drop=True)

    def quote(self, symbol: str) -> tuple[datetime, float, float]:
        # El plan gratuito da cotizaciones en tiempo real solo de IEX; alcanza para el spread de un ETF grande.
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
        last = self._call(self.data.get_stock_latest_quote, request)[symbol]
        return self._now(), float(last.bid_price), float(last.ask_price)

    def positions(self, magic: int, symbol: str | None = None) -> list[BrokerPosition]:
        held = {p.symbol: p for p in self._call(self.trading.get_all_positions)}
        entries, closes = self._bot_orders(magic)
        found = []
        for ticket, entry in entries.items():
            position = held.get(entry.symbol)
            if (symbol and entry.symbol != symbol) or not _filled(entry) or position is None:
                continue
            if self._exit_fills(entry, closes.get(ticket, [])) or abs(float(position.qty)) != float(entry.filled_qty):
                continue
            legs = entry.legs or []
            stop = next((leg for leg in legs if _value(leg.type) in ("stop", "stop_limit")), None)
            target = next((leg for leg in legs if _value(leg.type) == "limit"), None)
            found.append(BrokerPosition(
                ticket=ticket, symbol=entry.symbol, volume=float(entry.filled_qty),
                price_open=float(position.avg_entry_price),
                sl=float(stop.stop_price) if stop else None, tp=float(target.limit_price) if target else None,
                profit=float(position.unrealized_pl or 0), magic=magic, is_buy=_value(entry.side) == "buy",
                stop_leg_id=str(stop.id) if stop else None,
                open_leg_ids=tuple(str(leg.id) for leg in legs if _value(leg.status) not in FINISHED),
                closing=any(_value(c.status) not in FINISHED for c in closes.get(ticket, [])),
            ))
        return found

    def today_deals(self, magic: int, server_now: datetime) -> tuple[float, int]:
        """(resultado del día sin el flotante, entradas del día). Así el motor calcula pnl_today = equity - last_equity."""
        last_equity = float(self._call(self.trading.get_account).last_equity)
        balance, _ = self.balance_and_equity()
        entries, _ = self._bot_orders(magic)
        today = sum(1 for e in entries.values() if e.filled_at and _new_york(e.filled_at).date() == server_now.date())
        return balance - last_equity, today

    def bot_deals(self, magic: int, since: datetime) -> list[dict]:
        """Entradas y salidas de las posiciones del bot (incluidos SL y TP que ejecuta el servidor), como en MT5."""
        entries, closes = self._bot_orders(magic, since)
        deals = []
        for ticket, entry in entries.items():
            if not _filled(entry):
                continue
            price_in, direction = float(entry.filled_avg_price), 1 if _value(entry.side) == "buy" else -1
            deals.append(self._deal(ticket, entry, True, 0.0))
            for exit_order in self._exit_fills(entry, closes.get(ticket, [])):
                money = (float(exit_order.filled_avg_price) - price_in) * float(exit_order.filled_qty) * direction
                deals.append(self._deal(ticket, exit_order, False, money))
        return deals

    def send_market_order(self, plan: OrderPlan, magic: int, comment: str):
        signal, ticket = plan.signal, int(clock.time() * 1000)
        request = MarketOrderRequest(
            symbol=signal.symbol, qty=int(plan.lots), side=OrderSide.BUY if signal.side == "buy" else OrderSide.SELL,
            type=OrderType.MARKET, time_in_force=TimeInForce.GTC, order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(signal.target, 2)),
            stop_loss=StopLossRequest(stop_price=round(signal.stop, 2)),
            client_order_id=f"{magic}-open-{ticket}",
        )
        order = self._call(self.trading.submit_order, request)
        order = self._wait(order.id, _filled)
        price = float(order.filled_avg_price) if order.filled_avg_price else None
        return SimpleNamespace(order=ticket, price=price)

    def modify_stop(self, position: BrokerPosition, new_stop: float):
        if position.stop_leg_id is None:
            raise AlpacaError(f"{position.symbol}: la posición {position.ticket} no tiene orden de stop")
        return self._call(self.trading.replace_order_by_id, position.stop_leg_id,
                          ReplaceOrderRequest(stop_price=round(new_stop, 2)))

    def close_position(self, position: BrokerPosition, comment: str):
        # Las acciones del SL y el TP están reservadas: primero se cancelan (cancelar una cancela la otra) y luego se
        # vende. Fuera de horario la orden queda en cola para la apertura siguiente; no se manda otra encima.
        if position.closing:
            return None
        if position.open_leg_ids:
            self._call(self.trading.cancel_order_by_id, position.open_leg_ids[0])
            for leg_id in position.open_leg_ids:
                self._wait(leg_id, lambda o: _value(o.status) in FINISHED)
        request = MarketOrderRequest(
            symbol=position.symbol, qty=position.volume, side=OrderSide.SELL if position.is_buy else OrderSide.BUY,
            type=OrderType.MARKET, time_in_force=TimeInForce.DAY,
            client_order_id=f"{position.magic}-close-{position.ticket}-{int(clock.time() * 1000)}",
        )
        return self._call(self.trading.submit_order, request)

    def position_is_buy(self, position: BrokerPosition) -> bool:
        return position.is_buy

    def _forming_session(self) -> tuple[date, datetime]:
        now = self._now()
        if self._calendar is None or self._calendar[0] != now.date():
            request = GetCalendarRequest(start=now.date() - timedelta(days=10), end=now.date())
            self._calendar = (now.date(), self._call(self.trading.get_calendar, request))
        started = [s for s in self._calendar[1] if _new_york(s.open) <= now]
        if not started:
            raise AlpacaError("el calendario de Alpaca no trae sesiones recientes")
        return started[-1].date, _new_york(started[-1].open)

    def _daily_bars(self, symbol: str, timeframe: str, start: date) -> pd.DataFrame:
        if timeframe != "D1":
            raise AlpacaError(f"el conector de Alpaca solo maneja velas D1, no {timeframe}")
        request = StockBarsRequest(
            symbol_or_symbols=symbol, timeframe=TimeFrame.Day, adjustment=Adjustment.ALL, feed=DataFeed.SIP,
            start=datetime.combine(start, datetime.min.time(), NEW_YORK), end=datetime.now(timezone.utc) - SIP_DELAY,
        )
        found = self._call(self.data.get_stock_bars, request).data.get(symbol, [])
        bars = pd.DataFrame([{
            "time": _new_york(b.timestamp).replace(hour=0, minute=0, second=0, microsecond=0),
            "open": b.open, "high": b.high, "low": b.low, "close": b.close, "tick_volume": b.volume, "spread": 0,
        } for b in found], columns=["time", "open", "high", "low", "close", "tick_volume", "spread"])
        bars["time"] = pd.to_datetime(bars["time"])
        return bars

    def _bot_orders(self, magic: int, since: datetime | None = None) -> tuple[dict, dict]:
        """Órdenes del bot: entradas por ticket (con sus patas SL/TP) y cierres por ticket."""
        request = GetOrdersRequest(status=QueryOrderStatus.ALL, nested=True, limit=MAX_ORDERS, after=since)
        entries, closes = {}, {}
        for order in self._call(self.trading.get_orders, request):
            parsed = _parse_id(order.client_order_id, magic)
            if parsed and parsed[0] == "open":
                entries[parsed[1]] = order
            elif parsed:
                closes.setdefault(parsed[1], []).append(order)
        return entries, closes

    @staticmethod
    def _exit_fills(entry, closes: list) -> list:
        return [o for o in [*(entry.legs or []), *closes] if _filled(o)]

    @staticmethod
    def _deal(ticket: int, order, is_entry: bool, money: float) -> dict:
        return {"position": ticket, "symbol": order.symbol, "time": _new_york(order.filled_at), "entry": is_entry,
                "side": _value(order.side), "price": float(order.filled_avg_price),
                "volume": float(order.filled_qty), "money": money}

    def _wait(self, order_id, done):
        """Consulta la orden hasta que cumpla `done` o pasen WAIT_SECONDS; devuelve el último estado."""
        deadline = clock.time() + WAIT_SECONDS
        while True:
            order = self._call(self.trading.get_order_by_id, order_id)
            if done(order) or clock.time() > deadline:
                return order
            clock.sleep(0.5)

    @staticmethod
    def _call(function, *args):
        try:
            return function(*args)
        except (APIError, RequestException) as error:
            raise AlpacaError(f"Alpaca: {error}") from error
