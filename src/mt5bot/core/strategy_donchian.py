"""Ruptura del canal de Donchian a favor de la tendencia.

Compra cuando el cierre supera el máximo de las channel_bars velas anteriores y está
sobre la EMA de tendencia; venta al revés. Stop a stop_atr x ATR. La salida es por
trailing (ver position_rules.next_stop), no por objetivo.
"""
import pandas as pd

from mt5bot.config import StrategyConfig
from mt5bot.core.indicators import atr, ema
from mt5bot.core.models import Signal


def bars_needed(cfg: StrategyConfig) -> int:
    # Dos periodos de la EMA para que el valor inicial ya no pese (< 2 %).
    return 2 * cfg.donchian.trend_ema + cfg.donchian.channel_bars


def find_signal(symbol: str, bars: pd.DataFrame, cfg: StrategyConfig) -> Signal | None:
    """Evalúa la última vela de bars (velas cerradas). Sin historial suficiente no hay señal."""
    params = cfg.donchian
    if len(bars) < bars_needed(cfg):
        return None

    last = bars.iloc[-1]
    previous = bars.iloc[-params.channel_bars - 1:-1]
    channel_high, channel_low = previous["high"].max(), previous["low"].min()
    trend = ema(bars["close"], params.trend_ema).iloc[-1]
    risk = params.stop_atr * atr(bars, cfg.atr_period).iloc[-1]

    close = float(last["close"])
    if close > channel_high and close > trend:
        side, stop = "buy", close - risk
    elif close < channel_low and close < trend:
        side, stop = "sell", close + risk
    else:
        return None

    direction = 1 if side == "buy" else -1
    return Signal(
        symbol=symbol,
        side=side,
        bar_time=last["time"].to_pydatetime(),
        entry=close,
        stop=stop,
        target=close + direction * cfg.target_r * risk,
        reason=f"cierre {close:.5f} rompe canal {channel_low:.5f}-{channel_high:.5f}, EMA{params.trend_ema} {trend:.5f}",
    )
