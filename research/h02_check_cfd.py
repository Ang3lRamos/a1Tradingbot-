"""H02 - Verificación con precios operables: ¿el adelanto aparece en el CFD o solo en la apertura del índice?

La apertura de un índice se calcula con acciones que aún no abrieron (precios de ayer): reacciona tarde.
El CFD de GNT ya refleja todo a la hora de apertura. Se comparan ambos en el mismo periodo (2025-2026).
"""
from pathlib import Path

import pandas as pd

import lab
from h02_lead_lag import STRONG_MOVE, leader_signal

GNT_DATA = Path(__file__).parents[1] / "data"
SESSIONS = {  # mercado seguidor: (CFD de GNT, zona horaria, apertura, último cierre horario de la sesión)
    "N225": ("JP225.z", "Asia/Tokyo", 9, 15),
    "DAX": ("DE40.z", "Europe/Berlin", 9, 17),
}
CFD_ROUNDTRIP = {"N225": 0.00037, "DAX": 0.00013}  # spread + USD 10/lote sobre el nominal de 1 lote


def cfd_sessions(follower: str) -> pd.DataFrame:
    """Apertura y cierre de la sesión local de cada día con precios del CFD (hora servidor = Nueva York + 5 h)."""
    symbol, zone, open_hour, close_hour = SESSIONS[follower]
    bars = pd.read_csv(GNT_DATA / f"{symbol}_H1.csv", parse_dates=["time"])
    ny = (bars.time - pd.Timedelta(hours=5)).dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    local = ny.dt.tz_convert(zone)
    bars["date"], bars["hour"] = local.dt.tz_localize(None).dt.normalize(), local.dt.hour
    opens = bars[bars.hour == open_hour].groupby("date").open.first()
    closes = bars[bars.hour == close_hour - 1].groupby("date").close.last()
    return pd.DataFrame({"open": opens, "close": closes}).dropna()


def session_net(position: pd.Series, sessions: pd.DataFrame, roundtrip: float) -> pd.Series:
    position = position.reindex(sessions.index).fillna(0)
    return position * (sessions.close / sessions.open - 1) - roundtrip * (position != 0)


if __name__ == "__main__":
    cases = {"H02a SPX->N225": ("SPX", "N225", False), "H02b SPX->DAX": ("SPX", "DAX", False),
             "H02c N225->DAX": ("N225", "DAX", True)}
    trials = 0
    for case, (leader, follower, same_day) in cases.items():
        cfd = cfd_sessions(follower)
        index_bars = lab.load(follower)
        index_bars = index_bars[(index_bars.index >= cfd.index.min()) & (index_bars.index <= cfd.index.max())]
        for variant, threshold in (("todos", 0.0), ("fuertes", STRONG_MOVE)):
            results = {}
            for source, sessions, roundtrip in (("índice Yahoo", index_bars, lab.costs_for(follower)[0]),
                                                ("CFD GNT", cfd, CFD_ROUNDTRIP[follower])):
                signal = leader_signal(leader, sessions.index, same_day)
                position = signal.apply(lambda r: 1.0 if r > threshold else (-1.0 if r < -threshold else 0.0))
                net = session_net(position, sessions, roundtrip)
                active = net[position.reindex(sessions.index).fillna(0) != 0]
                t = active.mean() / (active.std() / len(active) ** 0.5) if len(active) > 2 else float("nan")
                results[source] = {"dias": len(active), "media_pct": round(float(100 * active.mean()), 3),
                                   "t": round(float(t), 2)}
            trials = lab.register("H02 adelanto entre mercados", f"{case} {variant} CFD vs índice",
                                  "verificacion_2025_2026", results, None)
            print(f"{case:15} {variant:8} índice: {results['índice Yahoo']} | CFD: {results['CFD GNT']}")
    print(f"\nPruebas en el registro: {trials}")
