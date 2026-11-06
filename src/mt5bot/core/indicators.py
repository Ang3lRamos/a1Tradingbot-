"""Indicadores calculados igual que en MT5, para que backtest y terminal coincidan."""
import pandas as pd


def ema(values: pd.Series, period: int) -> pd.Series:
    return values.ewm(span=period, adjust=False).mean()


def rsi(values: pd.Series, period: int) -> pd.Series:
    """RSI con el suavizado de Wilder, como iRSI de MT5."""
    change = values.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss)


def atr(bars: pd.DataFrame, period: int) -> pd.Series:
    # iATR de MT5 es la media SIMPLE del rango verdadero, no la suavizada de Wilder.
    prev_close = bars["close"].shift()
    true_range = pd.concat([bars["high"] - bars["low"],
                            (bars["high"] - prev_close).abs(),
                            (bars["low"] - prev_close).abs()], axis=1).max(axis=1)
    return true_range.rolling(period).mean()
