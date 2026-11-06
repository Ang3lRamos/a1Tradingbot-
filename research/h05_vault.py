"""H05 - CAJA FUERTE 2022-2024. Se corre UNA sola vez, con el código y parámetros de h05_tokyo_fade.py sin cambios.

Criterio fijado antes de abrir: H05a aprueba si gana después de costos Y su p al azar es < 0.05.
H05b se informa, pero no decide.
"""
import numpy as np

import lab
from h02_lead_lag import STRONG_MOVE, leader_signal
from h05_tokyo_fade import NULL_RUNS, tokyo_sessions

if __name__ == "__main__":
    sessions = tokyo_sessions()
    sessions = sessions[(sessions.index >= "2022-01-01") & (sessions.index <= "2024-12-31")]
    us = leader_signal("SPX", sessions.index, same_day=False)
    move = sessions.close / sessions.open - 1
    roundtrip = lab.costs_for("JPN225")[0]
    rng = np.random.default_rng(5)
    for variant, threshold in (("H05a fuertes", STRONG_MOVE), ("H05b todos", 0.0)):
        direction = -np.sign(us.where(us.abs() > threshold))
        active = direction.dropna()
        active = active[active != 0]
        r = active * move.reindex(active.index) - roundtrip
        flip = -active * move.reindex(active.index) - roundtrip
        pick = rng.random((NULL_RUNS, len(r))) < 0.5
        null = np.where(pick, r.to_numpy(), flip.to_numpy()).mean(axis=1)
        p = (np.sum(null >= r.mean()) + 1) / (NULL_RUNS + 1)
        t = r.mean() / (r.std() / np.sqrt(len(r)))
        result = {"n": len(r), "gana_pct": round(float(100 * (r > 0).mean()), 1),
                  "media_pct": round(float(100 * r.mean()), 3), "t": round(float(t), 2)}
        lab.register("H05 fade apertura Tokio", variant, "caja_fuerte_2022_2024", result, p)
        by_year = {int(y): round(float(100 * g.mean()), 3) for y, g in r.groupby(r.index.year)}
        print(f"{variant:13} {result} p_azar={p:.4f} | media % por año {by_year}")
        if variant.startswith("H05a"):
            passed = r.mean() > 0 and p < 0.05
            print(f"   VEREDICTO H05a: {'APRUEBA' if passed else 'NO APRUEBA'}")
