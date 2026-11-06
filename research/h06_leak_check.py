"""Diagnóstico de fuga de información en H06: acierto de dirección al quitar datos sospechosos.

No es una prueba de estrategia (no va al registro): busca datos que traen información del futuro.
"""
import pandas as pd

import h06_ml_daily as h06

SUSPECTS = {
    "todos los datos": [],
    "sin spx_r1": ["spx_r1"],
    "sin ibs": ["ibs"],
    "sin spx_r1 ni ibs": ["spx_r1", "ibs"],
}


def accuracy(data: pd.DataFrame, drop: list[str]) -> float:
    preds = h06.walk_forward(data.drop(columns=drop), "logistica")
    merged = preds.reset_index().merge(data[["target", "market"]].reset_index(), on=["time", "market"])
    return ((merged.p > 0.5) == (merged.target == 1)).mean()


if __name__ == "__main__":
    for asset_class, markets in h06.CLASSES.items():
        data = h06.dataset(markets)
        row = " | ".join(f"{label}: {100 * accuracy(data, drop):.1f} %" for label, drop in SUSPECTS.items())
        print(f"{asset_class:8} {row}")
