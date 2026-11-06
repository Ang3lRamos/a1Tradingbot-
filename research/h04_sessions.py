"""H04 - Relevo de sesiones: rango asiático y apertura de Londres. Velas M15 de MetaQuotes, hora en UTC.

Rango asiático: máximo y mínimo entre 00:00 y 07:00 UTC. Se busca el primer cierre M15 fuera del rango
en las 3 primeras horas desde la apertura de Londres (08:00 hora de Londres). Entrada a la apertura siguiente.
H04a  Ruptura: a favor de la salida; stop en el punto medio del rango.
H04b  Falsa ruptura: en contra de la salida; stop en el extremo de la vela que rompió.
Salida: stop, o el último cierre antes de las 16:00 de Londres. Costos GNT en R.
Barra del azar: las mismas entradas con dirección al azar (stop a la misma distancia).
"""
import sys

import numpy as np
import pandas as pd

import lab

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD"]
NULL_RUNS = 5000


def outcome(path: pd.DataFrame, direction: int, entry: float, risk: float) -> float:
    """Precio de salida: stop (o apertura si hay gap más allá) o último cierre de la ventana."""
    stop = entry - direction * risk
    for bar in path.itertuples(index=False):
        adverse = bar.low if direction == 1 else bar.high
        if (stop - adverse) * direction >= 0:
            return min(bar.open, stop) if direction == 1 else max(bar.open, stop)
    return path.close.iloc[-1]


def day_trades(day: pd.DataFrame, london_open: pd.Timestamp, london_close: pd.Timestamp, symbol: str):
    asian = day[(day.utc.dt.hour < 7)]
    if len(asian) < 20:
        return []
    high, low = asian.high.max(), asian.low.min()
    window = day[(day.utc >= london_open) & (day.utc < london_open + pd.Timedelta(hours=3))]
    broke = window[(window.close > high) | (window.close < low)]
    if broke.empty:
        return []
    signal = broke.iloc[0]
    after = day[(day.utc > signal.utc) & (day.utc < london_close)]
    if len(after) < 2:
        return []
    entry = after.open.iloc[0]
    up = signal.close > high
    roundtrip = lab.costs_for(symbol)[0] * entry
    trades = []
    for variant, direction, risk in (
        ("H04a ruptura", 1 if up else -1, abs(entry - (high + low) / 2)),
        ("H04b falsa ruptura", -1 if up else 1, (signal.high - entry) if up else (entry - signal.low)),
    ):
        if risk <= 0:
            continue
        r_real = ((outcome(after, direction, entry, risk) - entry) * direction - roundtrip) / risk
        r_flip = ((outcome(after, -direction, entry, risk) - entry) * -direction - roundtrip) / risk
        trades.append({"variant": variant, "symbol": symbol, "date": signal.utc.normalize(), "r": r_real, "r_flip": r_flip})
    return trades


def symbol_trades(symbol: str) -> pd.DataFrame:
    bars = lab.load_intraday(symbol)
    bars = bars[bars.utc.dt.dayofweek < 5]
    rows = []
    for date, day in bars.groupby(bars.utc.dt.date):
        london = pd.Timestamp(date).tz_localize("Europe/London")
        london_open = (london + pd.Timedelta(hours=8)).tz_convert("UTC")
        london_close = (london + pd.Timedelta(hours=16)).tz_convert("UTC")
        rows += day_trades(day, london_open, london_close, symbol)
    return pd.DataFrame(rows)


def null_p(trades: pd.DataFrame, rng) -> float:
    real = trades.r.mean()
    pick = rng.random((NULL_RUNS, len(trades))) < 0.5
    means = np.where(pick, trades.r.to_numpy(), trades.r_flip.to_numpy()).mean(axis=1)
    return (np.sum(means >= real) + 1) / (NULL_RUNS + 1)


def summary(g: pd.DataFrame) -> dict:
    t = g.r.mean() / (g.r.std() / np.sqrt(len(g)))
    return {"n": len(g), "gana_pct": round(float(100 * (g.r > 0).mean()), 1),
            "avg_r": round(float(g.r.mean()), 3), "t": round(float(t), 2)}


if __name__ == "__main__":
    symbols = sys.argv[1:] or SYMBOLS
    trades = pd.concat([symbol_trades(s) for s in symbols], ignore_index=True)
    explore = trades[trades.date <= pd.Timestamp(lab.PERIODS["exploracion"][1], tz="UTC")]
    rng = np.random.default_rng(3)
    trials = 0
    for variant, g in explore.groupby("variant"):
        result, p = summary(g), null_p(g, rng)
        trials = lab.register("H04 relevo de sesiones", f"{variant} {'+'.join(symbols)}", "exploracion", result, p)
        print(f"{variant:20} {result} p_azar={p:.4f}")
        for symbol, gs in g.groupby("symbol"):
            print(f"   {symbol:7} {summary(gs)}")
    print(f"\nPruebas en el registro: {trials}. Barra corregida: p < {lab.required_p(trials):.5f}")
