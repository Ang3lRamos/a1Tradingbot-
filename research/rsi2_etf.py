"""RSI2 sobre un ETF del S&P 500 con acciones fraccionadas: 100 % del capital en cada señal, sin apalancamiento.

Sin lote mínimo (fraccionadas), sin swap (no es CFD) y casi sin costo (spread ~1 punto básico).
Entrada y salida al cierre del día de la señal. Datos del índice S&P 500 desde 1990 (Yahoo, en caché del laboratorio).
"""
import numpy as np
import pandas as pd

import lab

SPREAD_PCT = 0.0001


def rsi2(close: pd.Series) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def daily_returns(close: pd.Series) -> tuple[pd.Series, list[float]]:
    """Retorno diario de la cuenta y retorno de cada operación."""
    sma200, sma5, r2 = close.rolling(200).mean(), close.rolling(5).mean(), rsi2(close)
    move = close.pct_change().shift(-1).fillna(0)        # lo que gana una posición tomada al cierre de hoy
    rets, trades, held, entry = np.zeros(len(close)), [], 0, 0.0
    for i in range(len(close) - 1):
        if held == 0 and close.iloc[i] > sma200.iloc[i] and r2.iloc[i] < 10:
            held, entry = 1, close.iloc[i]
            rets[i] -= SPREAD_PCT
        if held:
            rets[i] += move.iloc[i]
            held += 1
            if close.iloc[i + 1] > sma5.iloc[i + 1] or held > 10:
                trades.append(close.iloc[i + 1] / entry - 1)
                held = 0
    return pd.Series(rets, index=close.index), trades


def growth(series: pd.Series) -> tuple[float, float]:
    equity = (1 + series).cumprod()
    years = (series.index[-1] - series.index[0]).days / 365.25
    return equity.iloc[-1] ** (1 / years) - 1, (equity / equity.cummax() - 1).min()


if __name__ == "__main__":
    close = lab.load("SPX").close
    strategy, trades = daily_returns(close)
    strategy = strategy[strategy.index >= "1990-01-01"]
    hold = close.pct_change().fillna(0)
    hold = hold[hold.index >= "1990-01-01"]
    for label, series in (("RSI2, 100 % del capital por señal", strategy), ("Comprar y mantener el S&P 500", hold)):
        cagr, dd = growth(series)
        print(f"{label:34} crecimiento anual {100 * cagr:4.1f} % | peor caída {100 * dd:6.1f} % | "
              f"en mercado {100 * (series != 0).mean():3.0f} % de los días")
    trades = np.array(trades[-len(trades):])
    print(f"operaciones: {len(trades)} ({len(trades) / 36:.0f} al año) | ganadoras {100 * (trades > 0).mean():.0f} % | "
          f"media por operación {100 * trades.mean():+.2f} %")
