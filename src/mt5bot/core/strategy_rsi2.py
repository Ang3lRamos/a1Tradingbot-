"""Compra de caídas en tendencia alcista (RSI de 2 periodos, Connors). Solo compras, pensada para índices en D1.

Entra cuando el cierre está sobre la media de trend_sma y el RSI(rsi_period) cae bajo entry_below: una caída
fuerte de pocos días dentro de una tendencia alcista. Sale por regla, no por objetivo: al primer cierre sobre
la media de exit_sma o tras max_bars velas. El stop a stop_atr x ATR es de emergencia.
Validada con datos de 1990-2026 (research/rsi2_long_history.py): ventaja pequeña y pérdidas en crisis.
"""
from datetime import datetime

import pandas as pd

from mt5bot.config import StrategyConfig
from mt5bot.core.indicators import atr, rsi
from mt5bot.core.models import Signal


SATURDAY = 5


def bars_needed(cfg: StrategyConfig) -> int:
    # Holgura para las velas de fin de semana que se descartan (GNT tiene una vela D1 de 1 hora los domingos).
    return int(cfg.rsi2.trend_sma * 1.25) + 20


def weekday_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Solo días hábiles: la vela corta del domingo (reapertura) distorsiona RSI y medias diarias."""
    return bars[bars["time"].dt.day_of_week < SATURDAY]


def find_signal(symbol: str, bars: pd.DataFrame, cfg: StrategyConfig) -> Signal | None:
    """Evalúa la última vela hábil de bars (velas cerradas). Sin historial suficiente no hay señal."""
    params = cfg.rsi2
    bars = weekday_bars(bars)
    if len(bars) < params.trend_sma + 20:
        return None
    close = float(bars["close"].iloc[-1])
    trend = bars["close"].rolling(params.trend_sma).mean().iloc[-1]
    oscillator = rsi(bars["close"], params.rsi_period).iloc[-1]
    if not (close > trend and oscillator < params.entry_below):
        return None
    risk = params.stop_atr * atr(bars, cfg.atr_period).iloc[-1]
    return Signal(
        symbol=symbol,
        side="buy",
        bar_time=bars["time"].iloc[-1].to_pydatetime(),
        entry=close,
        stop=close - risk,
        target=close + cfg.target_r * risk,
        reason=f"RSI{params.rsi_period} {oscillator:.1f} < {params.entry_below} sobre SMA{params.trend_sma} {trend:.2f}",
    )


def exit_due(bars: pd.DataFrame, opened_at: datetime, cfg: StrategyConfig) -> bool:
    """True si la última vela cerró sobre la media de salida o la posición ya cumplió max_bars velas."""
    params = cfg.rsi2
    bars = weekday_bars(bars)
    times = bars["time"]
    started = times[times <= pd.Timestamp(opened_at)]
    held = int((times >= started.iloc[-1]).sum()) if not started.empty else 0
    above_exit_mean = bars["close"].iloc[-1] > bars["close"].rolling(params.exit_sma).mean().iloc[-1]
    return bool(above_exit_mean) or held >= params.max_bars
