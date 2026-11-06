"""H03 - Cambio de régimen por volatilidad. Solo caja de EXPLORACIÓN. Solo compras, cierre a cierre.

Mercados nerviosos sobrerreaccionan y se devuelven; mercados tranquilos siguen su tendencia.
H03a  Solo tendencia: comprado si el cierre está sobre la media de 50 días.
H03b  Solo RSI2: compra con RSI2 < 10 sobre la media de 200, sale al cerrar sobre la media de 5 (máx. 10 días).
H03c  Cambio de régimen: si la volatilidad de 20 días supera su mediana del último año, RSI2 (sin filtro de 200);
      si no, tendencia de 50 días.
"""
import numpy as np
import pandas as pd

import lab

INDICES = ["SPX", "NDX", "DJI", "DAX", "N225", "FTSE"]


def rsi2(close: pd.Series) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def mean_reversion_position(close: pd.Series, allowed: pd.Series, use_trend_filter: bool) -> pd.Series:
    """Estado comprado/fuera de RSI2, decidido en cada cierre. Solo entra donde allowed es verdadero."""
    sma5, sma200, r2 = close.rolling(5).mean(), close.rolling(200).mean(), rsi2(close)
    entry = (r2 < 10) & allowed & ((close > sma200) if use_trend_filter else True)
    position, held = np.zeros(len(close)), 0
    for i in range(len(close)):
        if held:
            held += 1
            if close.iloc[i] > sma5.iloc[i] or held > 10:
                held = 0
                continue
            position[i] = 1
        elif entry.iloc[i]:
            held, position[i] = 1, 1
    return pd.Series(position, index=close.index)


def variants(close: pd.Series) -> dict[str, pd.Series]:
    trend = (close > close.rolling(50).mean()).astype(float)
    vol20 = close.pct_change().rolling(20).std()
    nervous = vol20 > vol20.rolling(252).median()
    always = pd.Series(True, index=close.index)
    return {
        "H03a tendencia": trend,
        "H03b RSI2": mean_reversion_position(close, always, use_trend_filter=True),
        "H03c régimen": mean_reversion_position(close, nervous, use_trend_filter=False).where(nervous, trend.where(~nervous, 0)),
    }


if __name__ == "__main__":
    trials = 0
    for name in INDICES:
        close = lab.load(name).close
        for variant, position in variants(close).items():
            daily = lab.in_period(lab.strategy_returns(position, close, name), "exploracion")
            result = lab.stats(daily)
            p = lab.null_pvalue(position, close, name, "exploracion", runs=1000)
            trials = lab.register("H03 régimen de volatilidad", f"{variant} {name}", "exploracion", result, p)
            print(f"{name:5} {variant:15} {result} p_azar={p:.4f}")
    print(f"\nPruebas en el registro: {trials}. Barra corregida: p < {lab.required_p(trials):.4f}")
