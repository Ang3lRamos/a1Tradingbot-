"""Ruptura del rango de apertura (opening range breakout).

El rango es el máximo y mínimo de las velas entre range_start y range_end.
La señal es el primer cierre fuera del rango antes de entry_until. Si la
primera ruptura ya pasó, no se busca otra ese día: así se evita entrar tarde
en un movimiento que ya ocurrió.
"""
import pandas as pd

from mt5bot.config import OrbConfig, StrategyConfig
from mt5bot.core.models import Signal


def bars_needed(cfg: StrategyConfig) -> int:
    return 288  # un día completo incluso en M5


def opening_range(day_bars: pd.DataFrame, cfg: OrbConfig) -> tuple[float, float] | None:
    times = day_bars["time"].dt.time
    in_range = day_bars[(times >= cfg.range_start) & (times < cfg.range_end)]
    if in_range.empty:
        return None
    return float(in_range["high"].max()), float(in_range["low"].min())


def find_signal(symbol: str, bars: pd.DataFrame, cfg: StrategyConfig) -> Signal | None:
    """bars: velas cerradas ordenadas por tiempo; se usan solo las del día de la última.

    Solo usa velas hasta la de la ruptura, así que el resultado no cambia si
    se le pasan velas posteriores del mismo día (no mira hacia el futuro).
    """
    day_bars = bars[bars["time"].dt.date == bars["time"].iloc[-1].date()]
    rng = opening_range(day_bars, cfg.orb)
    if rng is None:
        return None
    high, low = rng

    times = day_bars["time"].dt.time
    after_range = day_bars[times >= cfg.orb.range_end]
    for bar in after_range.itertuples(index=False):
        broke_up, broke_down = bar.close > high, bar.close < low
        if not (broke_up or broke_down):
            continue
        if bar.time.time() >= cfg.orb.entry_until:
            return None
        return _build_signal(symbol, bar, high, low, "buy" if broke_up else "sell", cfg)
    return None


def _build_signal(symbol, bar, high, low, side, cfg: StrategyConfig) -> Signal | None:
    entry = float(bar.close)
    if cfg.orb.stop_mode == "range_mid":
        stop = (high + low) / 2
    else:
        stop = low if side == "buy" else high

    risk = entry - stop if side == "buy" else stop - entry
    if risk <= 0:
        return None
    target = entry + cfg.target_r * risk if side == "buy" else entry - cfg.target_r * risk
    return Signal(
        symbol=symbol,
        side=side,
        bar_time=bar.time.to_pydatetime(),
        entry=entry,
        stop=stop,
        target=target,
        reason=f"cierre {entry:.5f} fuera del rango {low:.5f}-{high:.5f}",
    )
