"""H06 - Machine learning diario. Solo caja de EXPLORACIÓN, con predicciones walk-forward.

Predice si mañana cierra arriba (cierre t -> t+1) con 22 datos conocidos al cierre de hoy.
Un modelo por clase de activo (índices, FX) entrenado con todos sus mercados juntos.
Walk-forward: para cada año Y de 2000 a 2016 se entrena solo con datos anteriores a Y.
Modelos: regresión logística y gradient boosting (parámetros fijos, sin ajuste).
Reglas: "ls" compra si p > 0.52 y vende si p < 0.48; "lo" solo compra si p > 0.52.
Se evalúa la cartera con peso igual entre mercados, con costos y swap GNT, contra la barra del azar.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import lab

CLASSES = {
    "indices": ["SPX", "NDX", "DJI", "DAX", "N225", "FTSE"],
    "fx": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"],
}
YEARS = range(2000, 2017)
UPPER, LOWER = 0.52, 0.48
MODELS = {
    "logistica": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000)),
    "boosting": lambda: HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                       l2_regularization=1.0, random_state=0),
}


def rsi(close, n):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def features(bars: pd.DataFrame, spx_ret: pd.Series, use_range: bool) -> pd.DataFrame:
    c = bars.close
    ret = c.pct_change()
    vol20 = ret.rolling(20).std()
    f = pd.DataFrame(index=bars.index)
    for k in (1, 2, 3, 5, 10, 20, 60):
        f[f"r{k}"] = (c / c.shift(k) - 1) / (vol20 * np.sqrt(k))     # escalado por volatilidad: comparable entre mercados
    for k in (5, 20, 50, 200):
        f[f"d_sma{k}"] = (c / c.rolling(k).mean() - 1) / vol20
    f["rsi2"], f["rsi14"] = rsi(c, 2), rsi(c, 14)
    if use_range:
        f["ibs"] = (c - bars.low) / (bars.high - bars.low).replace(0, np.nan)
    f["vol20"], f["vol_ratio"] = vol20, vol20 / ret.rolling(60).std()
    f["dow"] = bars.index.dayofweek
    month = pd.Series(bars.index.to_period("M"), index=bars.index)
    f["tdom_start"] = month.groupby(month).cumcount() + 1
    f["tdom_end"] = month.groupby(month).cumcount(ascending=False) + 1
    f["spx_r1"] = spx_ret.reindex(bars.index).fillna(0) / vol20
    return f.replace([np.inf, -np.inf], np.nan)


def last_known_spx(index: pd.DatetimeIndex) -> pd.Series:
    """Retorno del S&P 500 del último día de EE. UU. anterior a cada fecha (ya conocido al cierre local)."""
    shifted = lab.load("SPX").close.pct_change().shift(1, freq="D")
    return shifted.reindex(index.union(shifted.index)).sort_index().ffill().reindex(index)


def dataset(markets: list[str]) -> pd.DataFrame:
    spx_same_day = lab.load("SPX").close.pct_change()
    frames = []
    for name in markets:
        bars = lab.load(name)
        if name == "SPX":
            spx = pd.Series(0.0, index=bars.index)
        elif name in ("NDX", "DJI"):
            spx = spx_same_day                    # cierran a la misma hora que el S&P 500
        else:
            # Tokio, Frankfurt y Londres cierran antes que Nueva York; en FX de Yahoo la hora de cierre no es segura.
            spx = last_known_spx(bars.index)
        # En FX de Yahoo el máximo y mínimo del día incluyen horas posteriores al cierre: el rango filtra el futuro.
        f = features(bars, spx, use_range=name not in CLASSES["fx"])
        f["target"] = (bars.close.shift(-1) > bars.close).astype(float).where(bars.close.shift(-1).notna())
        f["market"] = name
        frames.append(f)
    return pd.concat(frames).dropna()


def walk_forward(data: pd.DataFrame, model_name: str) -> pd.Series:
    """Probabilidad de subida para cada día de 2000-2016, con un modelo entrenado solo con años anteriores."""
    cols = [c for c in data.columns if c not in ("target", "market")]
    preds = []
    for year in YEARS:
        start = pd.Timestamp(f"{year}-01-01")
        # Se excluye el último día antes de Y: su objetivo es el primer cierre de Y.
        train = data[data.index < start - pd.Timedelta(days=4)]
        test = data[(data.index >= start) & (data.index < pd.Timestamp(f"{year + 1}-01-01"))]
        model = MODELS[model_name]().fit(train[cols], train["target"])
        preds.append(pd.DataFrame({"p": model.predict_proba(test[cols])[:, 1], "market": test["market"]}, index=test.index))
    return pd.concat(preds)


def portfolio_returns(positions: dict[str, pd.Series], closes: dict[str, pd.Series], shifts=None) -> pd.Series:
    daily = []
    for name, position in positions.items():
        if shifts is not None:
            position = pd.Series(np.roll(position.to_numpy(), shifts[name]), index=position.index)
        daily.append(lab.strategy_returns(position, closes[name], name).rename(name))
    combined = pd.concat(daily, axis=1)
    combined = combined[(combined.index >= "2000-01-01") & (combined.index <= "2016-12-31")]
    return combined.mean(axis=1)


if __name__ == "__main__":
    trials = 0
    rng = np.random.default_rng(11)
    for asset_class, markets in CLASSES.items():
        data = dataset(markets)
        closes = {name: lab.load(name).close for name in markets}
        for model_name in MODELS:
            preds = walk_forward(data, model_name)
            merged = preds.reset_index().merge(data[["target", "market"]].reset_index(), on=["time", "market"])
            accuracy = ((merged.p > 0.5) == (merged.target == 1)).mean()
            print(f"{asset_class:8} {model_name:9} acierto de dirección {100 * accuracy:.1f} % "
                  f"(días al alza: {100 * merged.target.mean():.1f} %)")
            for rule in ("ls", "lo"):
                positions = {}
                for name in markets:
                    p = preds[preds.market == name].p
                    pos = (p > UPPER).astype(float) - ((p < LOWER).astype(float) if rule == "ls" else 0.0)
                    positions[name] = pos.reindex(closes[name].index).fillna(0)
                real = portfolio_returns(positions, closes)
                result = lab.stats(real)
                null_means = []
                for _ in range(300):
                    shifts = {name: int(rng.integers(20, len(closes[name]) - 20)) for name in markets}
                    null_means.append(portfolio_returns(positions, closes, shifts).mean())
                p_value = (sum(m >= real.mean() for m in null_means) + 1) / (len(null_means) + 1)
                trials = lab.register("H06 machine learning diario", f"{asset_class} {model_name} {rule} corregido",
                                      "exploracion_walk_forward_2000_2016", result, p_value)
                print(f"{asset_class:8} {model_name:9} {rule}  {result} p_azar={p_value:.4f}")
    print(f"\nPruebas en el registro: {trials}. Barra corregida: p < {lab.required_p(trials):.4f}")
