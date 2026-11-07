"""Único módulo que habla con MetaTrader 5. Requiere Windows y el terminal abierto."""
from datetime import datetime, timedelta, timezone

import pandas as pd

from mt5bot.core.models import OrderPlan, SymbolSpec

TIMEFRAMES = {"M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15",
              "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4", "D1": "TIMEFRAME_D1"}
MAX_DEVIATION_POINTS = 20


class Mt5Error(RuntimeError):
    pass


def _naive_server_time(epoch_seconds: int) -> datetime:
    # MT5 entrega la hora del servidor codificada como si fuera UTC.
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).replace(tzinfo=None)


class Mt5Gateway:
    def __init__(self):
        import MetaTrader5
        self.mt5 = MetaTrader5

    def connect(self, login: int, password: str, server: str, path: str | None) -> None:
        kwargs = {"login": login, "password": password, "server": server}
        if path:
            kwargs["path"] = path
        if not self.mt5.initialize(**kwargs):
            raise Mt5Error(f"no se pudo conectar a MT5: {self.mt5.last_error()}")
        if not self.mt5.terminal_info().trade_allowed:
            raise Mt5Error("el trading algorítmico está desactivado en el terminal (botón Algo Trading)")

    def shutdown(self) -> None:
        self.mt5.shutdown()

    def is_demo_account(self) -> bool:
        return self.mt5.account_info().trade_mode == self.mt5.ACCOUNT_TRADE_MODE_DEMO

    def balance_and_equity(self) -> tuple[float, float]:
        info = self.mt5.account_info()
        return info.balance, info.equity

    def symbol_spec(self, symbol: str) -> SymbolSpec:
        if not self.mt5.symbol_select(symbol, True):
            raise Mt5Error(f"el símbolo {symbol} no existe en este broker")
        info = self.mt5.symbol_info(symbol)
        return SymbolSpec(
            name=symbol, digits=info.digits, point=info.point,
            tick_size=info.trade_tick_size, tick_value=info.trade_tick_value,
            volume_min=info.volume_min, volume_max=info.volume_max, volume_step=info.volume_step,
            contract_size=info.trade_contract_size, swap_long=info.swap_long, swap_short=info.swap_short,
            # MT5 numera los días desde el domingo (0); Python desde el lunes (0).
            swap_mode=info.swap_mode, swap_triple_weekday=(info.swap_rollover3days + 6) % 7,
        )

    def closed_bars(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Últimas velas cerradas. La posición 0 de MT5 es la vela en formación; se omite."""
        rates = self.mt5.copy_rates_from_pos(symbol, getattr(self.mt5, TIMEFRAMES[timeframe]), 1, count)
        if rates is None or len(rates) == 0:
            raise Mt5Error(f"sin velas para {symbol}: {self.mt5.last_error()}")
        bars = pd.DataFrame(rates)
        bars["time"] = pd.to_datetime(bars["time"], unit="s")
        return bars[["time", "open", "high", "low", "close", "tick_volume", "spread"]]

    def forming_bar_time(self, symbol: str, timeframe: str) -> datetime:
        """Apertura de la vela en formación (posición 0): tras un fin de semana es la reapertura del mercado."""
        rates = self.mt5.copy_rates_from_pos(symbol, getattr(self.mt5, TIMEFRAMES[timeframe]), 0, 1)
        if rates is None or len(rates) == 0:
            raise Mt5Error(f"sin vela en formación para {symbol}: {self.mt5.last_error()}")
        return _naive_server_time(int(rates[0]["time"]))

    def bars_range(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        rates = self.mt5.copy_rates_range(symbol, getattr(self.mt5, TIMEFRAMES[timeframe]), start, end)
        if rates is None or len(rates) == 0:
            raise Mt5Error(f"sin historial para {symbol}: {self.mt5.last_error()}")
        bars = pd.DataFrame(rates)
        bars["time"] = pd.to_datetime(bars["time"], unit="s")
        return bars[["time", "open", "high", "low", "close", "tick_volume", "spread"]]

    def quote(self, symbol: str) -> tuple[datetime, float, float]:
        """(hora del servidor, bid, ask) del último tick."""
        tick = self.mt5.symbol_info_tick(symbol)
        return _naive_server_time(tick.time), tick.bid, tick.ask

    def positions(self, magic: int, symbol: str | None = None) -> list:
        found = self.mt5.positions_get(symbol=symbol) if symbol else self.mt5.positions_get()
        return [p for p in (found or ()) if p.magic == magic]

    def today_deals(self, magic: int, server_now: datetime) -> tuple[float, int]:
        """(resultado cerrado del día, número de entradas del día) del bot."""
        start = server_now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = self.mt5.history_deals_get(start, server_now + timedelta(minutes=1)) or ()
        ours = [d for d in deals if d.magic == magic]
        realized = sum(d.profit + d.commission + d.swap for d in ours)
        entries = sum(1 for d in ours if d.entry == self.mt5.DEAL_ENTRY_IN)
        return realized, entries

    def bot_deals(self, magic: int, since: datetime) -> list[dict]:
        """Deals de las posiciones que abrió el bot, incluidas las salidas por SL/TP que ejecuta el servidor.

        Se buscan las posiciones por su deal de entrada con el magic del bot y luego todos sus deals,
        porque el broker no siempre copia el magic en el deal de salida.
        """
        found = self.mt5.history_deals_get(since, datetime.now() + timedelta(days=2)) or ()
        ours = {d.position_id for d in found if d.magic == magic and d.entry == self.mt5.DEAL_ENTRY_IN}
        return [{
            "position": d.position_id, "symbol": d.symbol, "time": _naive_server_time(d.time),
            "entry": d.entry == self.mt5.DEAL_ENTRY_IN, "side": "buy" if d.type == self.mt5.DEAL_TYPE_BUY else "sell",
            "price": d.price, "volume": d.volume, "money": d.profit + d.commission + d.swap + d.fee,
        } for d in found if d.position_id in ours]

    def send_market_order(self, plan: OrderPlan, magic: int, comment: str):
        signal = plan.signal
        is_buy = signal.side == "buy"
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": signal.symbol,
            "volume": plan.lots,
            "type": self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL,
            "price": signal.entry,
            "sl": self._round_price(signal.symbol, signal.stop),
            "tp": self._round_price(signal.symbol, signal.target),
            "deviation": MAX_DEVIATION_POINTS,
            "magic": magic,
            "comment": comment[:31],
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self._filling_mode(signal.symbol),
        }
        return self._send(request)

    def modify_stop(self, position, new_stop: float):
        return self._send({
            "action": self.mt5.TRADE_ACTION_SLTP,
            "position": position.ticket,
            "symbol": position.symbol,
            "sl": self._round_price(position.symbol, new_stop),
            "tp": position.tp,
        })

    def close_position(self, position, comment: str):
        _, bid, ask = self.quote(position.symbol)
        is_buy = position.type == self.mt5.POSITION_TYPE_BUY
        return self._send({
            "action": self.mt5.TRADE_ACTION_DEAL,
            "position": position.ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY,
            "price": bid if is_buy else ask,
            "deviation": MAX_DEVIATION_POINTS,
            "magic": position.magic,
            "comment": comment[:31],
            "type_filling": self._filling_mode(position.symbol),
        })

    def positions_without_stop(self, magic: int, symbol: str) -> list:
        return []  # en MT5 el SL vive en la posición y no vence

    def position_is_buy(self, position) -> bool:
        return position.type == self.mt5.POSITION_TYPE_BUY

    def _round_price(self, symbol: str, price: float) -> float:
        # El servidor rechaza precios con más decimales que el símbolo (stops calculados con ATR).
        return round(price, self.mt5.symbol_info(symbol).digits)

    def _filling_mode(self, symbol: str) -> int:
        # Cada broker acepta modos distintos; symbol_info.filling_mode es un bitmask (1=FOK, 2=IOC).
        allowed = self.mt5.symbol_info(symbol).filling_mode
        if allowed & 1:
            return self.mt5.ORDER_FILLING_FOK
        if allowed & 2:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def _send(self, request: dict):
        result = self.mt5.order_send(request)
        if result is None:
            raise Mt5Error(f"order_send sin respuesta: {self.mt5.last_error()}")
        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            raise Mt5Error(f"orden rechazada ({result.retcode}): {result.comment}")
        return result
