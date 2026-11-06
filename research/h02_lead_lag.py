"""H02 - Mercados que se adelantan a otros. Solo caja de EXPLORACIÓN.

La información de una sesión tarda en absorberse en la siguiente zona horaria (reacción lenta de inversionistas
locales). Se opera la sesión del mercado que sigue, de apertura a cierre, en la dirección del que lidera.

H02a  SPX de ayer (cierre a cierre)      -> Nikkei hoy (apertura a cierre)
H02b  SPX de ayer                        -> DAX hoy
H02c  Nikkei de hoy (cierra antes de que abra Europa) -> DAX hoy
Variantes: "todos" (cualquier movimiento) y "fuertes" (solo si el líder se movió más de 1 %).
"""
import pandas as pd

import lab

CASES = {
    "H02a SPX->N225": ("SPX", "N225", False),
    "H02b SPX->DAX": ("SPX", "DAX", False),
    "H02c N225->DAX": ("N225", "DAX", True),
}
STRONG_MOVE = 0.01


def leader_signal(leader: str, follower_index: pd.DatetimeIndex, same_day: bool) -> pd.Series:
    """Retorno del líder conocido antes de que abra el seguidor, alineado a las fechas del seguidor."""
    ret = lab.load(leader).close.pct_change()
    if same_day:
        return ret.reindex(follower_index)  # solo si el líder operó ese mismo día
    # El retorno del día d-1 (o del último día hábil anterior) es el último conocido cuando abre el seguidor el día d.
    shifted = ret.shift(1, freq="D")
    return shifted.reindex(follower_index.union(shifted.index)).sort_index().ffill().reindex(follower_index)


if __name__ == "__main__":
    trials = 0
    for case, (leader, follower, same_day) in CASES.items():
        bars = lab.load(follower)
        signal = leader_signal(leader, bars.index, same_day)
        for variant, threshold in (("todos", 0.0), ("fuertes", STRONG_MOVE)):
            position = signal.apply(lambda r: 1.0 if r > threshold else (-1.0 if r < -threshold else 0.0))
            daily = lab.in_period(lab.session_returns(position, bars, follower), "exploracion")
            result = lab.stats(daily)
            p = lab.null_pvalue(position, bars, follower, "exploracion", returns_fn=lab.session_returns)
            trials = lab.register("H02 adelanto entre mercados", f"{case} {variant}", "exploracion", result, p)
            print(f"{case:15} {variant:8} {result} p_azar={p:.4f}")
    print(f"\nPruebas en el registro: {trials}. Barra corregida: p < {lab.required_p(trials):.4f}")
