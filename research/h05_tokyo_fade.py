"""H05 - Apertura de Tokio en contra del día de EE. UU. CFD JPN225 (M15 de MetaQuotes), hora en UTC.

Nació mirando datos de GNT 2025-2026 (h02_check_cfd.py): esos años NO cuentan como evidencia.
JPN225 de MetaQuotes empieza en 2019-04, así que (fijado antes de correr): exploración de H05 = 2019-04 a 2021-12,
caja fuerte de H05 = 2022 a 2024. Muestra corta: cualquier conclusión es más débil que en H04.
Operación: a la apertura de las 9:00 de Tokio, en contra del signo del S&P 500 del último día de EE. UU.;
salida al cierre de las 15:00 de Tokio. Resultado en % del precio, con costos GNT.
H05a  Solo tras días fuertes de EE. UU. (|retorno| > 1 %).
H05b  Todos los días.
Barra del azar: los mismos días con dirección al azar.
"""
import numpy as np
import pandas as pd

import lab
from h02_lead_lag import STRONG_MOVE, leader_signal

NULL_RUNS = 5000


def tokyo_sessions() -> pd.DataFrame:
    bars = lab.load_intraday("JPN225")
    tokyo = bars.utc.dt.tz_convert("Asia/Tokyo")
    bars["date"], bars["hour"] = tokyo.dt.tz_localize(None).dt.normalize(), tokyo.dt.hour
    opens = bars[bars.hour == 9].groupby("date").open.first()
    closes = bars[bars.hour == 14].groupby("date").close.last()  # la última vela M15 de las 14:45 cierra a las 15:00
    return pd.DataFrame({"open": opens, "close": closes}).dropna()


if __name__ == "__main__":
    sessions = tokyo_sessions()
    print(f"sesiones JPN225: {len(sessions)} desde {sessions.index.min():%Y-%m-%d}")
    sessions = sessions[sessions.index <= "2021-12-31"]
    us = leader_signal("SPX", sessions.index, same_day=False)
    move = sessions.close / sessions.open - 1
    roundtrip = lab.costs_for("JPN225")[0]
    rng = np.random.default_rng(5)
    trials = 0
    for variant, threshold in (("H05a fuertes", STRONG_MOVE), ("H05b todos", 0.0)):
        direction = -np.sign(us.where(us.abs() > threshold))         # en contra de EE. UU.
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
        trials = lab.register("H05 fade apertura Tokio", variant, "exploracion_2019_2021", result, p)
        print(f"{variant:13} {result} p_azar={p:.4f}")
    print(f"\nPruebas en el registro: {trials}. Barra corregida: p < {lab.required_p(trials):.5f}")
