"""Laboratorio de investigación: datos largos, cajas de datos, costos GNT, barra del azar y registro de pruebas.

Reglas del protocolo:
- Exploración (hasta 2016): se prueba libremente.
- Validación (2017-2021): solo para elegir entre finalistas.
- Caja fuerte (2022 en adelante): se mira UNA vez por hipótesis final. Si falla, se descarta.
- Toda prueba se anota en registry.csv, incluidas las que fallan: el número de pruebas sube la barra.

Trampas conocidas de los datos de Yahoo (cada una produjo resultados falsos espectaculares):
- La apertura de un índice NO es un precio operable: se calcula con acciones que aún no abrieron (precios de ayer).
  Verificar con el CFD de GNT antes de creer cualquier efecto de apertura (H02: Sharpe 1.9 falso).
- SPX: la apertura es igual al cierre anterior en la mayoría de los días antes de 2010.
- FX: el máximo y el mínimo del día incluyen horas posteriores al cierre registrado; no usar rango ni IBS (H06).
- Tokio, Frankfurt y Londres cierran antes que Nueva York: el S&P 500 del mismo día es futuro para ellos (H06).
- Si algo da Sharpe > 1.5 o acierta más de 55 % la dirección diaria, buscar la fuga antes de celebrar.
"""
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path.home() / ".mt5bot" / "research_data"   # fuera de OneDrive
REGISTRY = Path(__file__).parent / "registry.csv"

PERIODS = {
    "exploracion": ("1990-01-01", "2016-12-31"),
    "validacion": ("2017-01-01", "2021-12-31"),
    "caja_fuerte": ("2022-01-01", "2100-01-01"),
}

# Ticker de Yahoo -> nombre interno. FX desde ~2003, índices desde los 80-90.
YAHOO = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "JPY=X", "AUDUSD": "AUDUSD=X",
    "USDCAD": "CAD=X", "USDCHF": "CHF=X", "NZDUSD": "NZDUSD=X",
    "SPX": "^GSPC", "NDX": "^NDX", "DJI": "^DJI", "DAX": "^GDAXI", "N225": "^N225", "FTSE": "^FTSE",
}

# Costo ida y vuelta (fracción del precio) y swap anual en % del nominal (largo, corto) en GNT.
# FX: spread ~1-2 pts + USD 10/lote; el swap FX de GNT no se midió y se toma 0 (operaciones de pocos días).
COSTS = {
    "fx": (0.00012, (0.0, 0.0)),
    # XAUUSD: spread ~0.2 USD + comisión 0.10 USD/onza sobre ~4000; swap no medido en %: solo para pruebas intradía.
    "XAUUSD": (0.00008, (0.0, 0.0)), "JPN225": (0.00037, (-3.48, -3.72)),
    "DE40": (0.00013, (-7.98, -2.35)), "US500": (0.00010, (-9.3, -9.79)),
    "SPX": (0.00010, (-9.3, -9.79)), "NDX": (0.00010, (-9.3, -9.79)), "DJI": (0.00010, (-9.3, -1.71)),
    "DAX": (0.00012, (-7.98, -2.35)), "N225": (0.00015, (-3.48, -3.72)), "FTSE": (0.00015, (-9.3, -2.35)),
}


def fetch_yahoo(name: str) -> Path:
    """Descarga velas diarias una sola vez y las deja en caché."""
    path = DATA_DIR / f"{name}_D1.csv"
    if path.exists():
        return path
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(YAHOO[name])}"
           f"?period1=0&period2={int(time.time())}&interval=1d")
    raw = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                                            timeout=60).read())
    result = raw["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    bars = pd.DataFrame({"time": pd.to_datetime(result["timestamp"], unit="s").normalize(),
                         "open": quote["open"], "high": quote["high"], "low": quote["low"], "close": quote["close"]})
    bars = bars.dropna().drop_duplicates("time", keep="last")
    bars = bars[(bars.high >= bars.low) & (bars.close > 0)]
    bars.to_csv(path, index=False)
    return path


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(fetch_yahoo(name), parse_dates=["time"]).set_index("time").sort_index()


def load_intraday(symbol: str) -> pd.DataFrame:
    """Velas M15 del terminal de MetaQuotes con la hora en UTC (el servidor usa horario de Atenas, UTC+2/+3)."""
    bars = pd.read_csv(DATA_DIR / f"mq_{symbol}_M15.csv", parse_dates=["time"])
    local = bars["time"].dt.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT")
    bars["utc"] = local.dt.tz_convert("UTC")
    return bars.dropna(subset=["utc"]).reset_index(drop=True)


def costs_for(name: str):
    return COSTS["fx"] if name not in COSTS else COSTS[name]


def in_period(series: pd.Series, period: str) -> pd.Series:
    start, end = PERIODS[period]
    return series[(series.index >= start) & (series.index <= end)]


def strategy_returns(position: pd.Series, close: pd.Series, name: str) -> pd.Series:
    """Retorno diario de cierre a cierre de una posición (-1, 0, 1) fijada al cierre de cada día.

    La posición del día t gana el movimiento de t a t+1. Se paga el costo ida y vuelta al abrir
    y el swap por cada noche (x3 si el siguiente día hábil está a 3 días).
    """
    roundtrip, (swap_long, swap_short) = costs_for(name)
    position = position.reindex(close.index).fillna(0)
    move = close.shift(-1) / close - 1
    nights = pd.Series(close.index, index=close.index).diff().shift(-1).dt.days.fillna(1)
    swap_rate = np.where(position > 0, swap_long, np.where(position < 0, swap_short, 0.0)) / 100 / 360
    opened = (position != 0) & (position != position.shift().fillna(0))
    gross = position * move
    net = gross + swap_rate * nights * (position != 0) - roundtrip * opened
    return net.fillna(0)


def session_returns(position: pd.Series, bars: pd.DataFrame, name: str) -> pd.Series:
    """Retorno de una posición abierta a la apertura y cerrada al cierre del mismo día (sin swap)."""
    roundtrip, _ = costs_for(name)
    position = position.reindex(bars.index).fillna(0)
    return (position * (bars.close / bars.open - 1) - roundtrip * (position != 0)).fillna(0)


def stats(daily: pd.Series) -> dict:
    active = daily[daily != 0]
    if len(active) < 20:
        return {"dias": len(active)}
    years = (daily.index[-1] - daily.index[0]).days / 365.25
    ann = (1 + daily).prod() ** (1 / years) - 1
    vol = daily.std() * np.sqrt(252)
    t = active.mean() / (active.std() / np.sqrt(len(active)))
    equity = (1 + daily).cumprod()
    return {"ret_anual_pct": round(float(100 * ann), 2), "vol_anual_pct": round(float(100 * vol), 2),
            "sharpe": round(float(ann / vol), 2) if vol else 0.0, "t": round(float(t), 2),
            "peor_caida_pct": round(float(100 * (equity / equity.cummax() - 1).min()), 1),
            "en_mercado_pct": round(100 * len(active) / len(daily), 1)}


def null_pvalue(position: pd.Series, prices, name: str, period: str, runs: int = 2000, seed: int = 7,
                returns_fn=None) -> float:
    """Fracción de versiones desplazadas al azar (mismas operaciones en otras fechas) que igualan o superan a la real.

    El desplazamiento circular conserva cuántas operaciones hay y cuánto duran: solo cambia CUÁNDO.
    prices es la serie de cierres (strategy_returns) o las velas (session_returns), según returns_fn.
    """
    returns_fn = returns_fn or strategy_returns
    real = in_period(returns_fn(position, prices, name), period).mean()
    rng = np.random.default_rng(seed)
    values = position.reindex(prices.index).fillna(0).to_numpy()
    better = 0
    for _ in range(runs):
        shifted = pd.Series(np.roll(values, rng.integers(20, len(values) - 20)), index=prices.index)
        if in_period(returns_fn(shifted, prices, name), period).mean() >= real:
            better += 1
    return (better + 1) / (runs + 1)


def register(hypothesis: str, variant: str, period: str, result: dict, p_value: float | None) -> int:
    """Anota la prueba y devuelve cuántas pruebas lleva el registro (la barra sube con ese número)."""
    new = not REGISTRY.exists()
    with REGISTRY.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(["fecha", "hipotesis", "variante", "periodo", "resultado", "p_azar"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), hypothesis, variant, period,
                         json.dumps(result, ensure_ascii=False), "" if p_value is None else round(p_value, 4)])
    with REGISTRY.open(encoding="utf-8") as f:
        return sum(1 for _ in f) - 1


def required_p(trials: int, alpha: float = 0.05) -> float:
    """Barra de significancia corregida por número de pruebas (Bonferroni: conservadora a propósito)."""
    return alpha / max(trials, 1)
