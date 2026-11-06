"""H01 - Flujos obligados de fin de mes. Solo caja de EXPLORACIÓN.

H01a  Índices, cambio de mes: sueldos y aportes a fondos de pensiones entran en los primeros días del mes.
      Compra desde el cierre del penúltimo día hábil hasta el cierre del 3.er día hábil del mes nuevo.
H01b  Variante de ventana: desde el cierre del último día hábil hasta el cierre del 4.º día hábil.
H01c  FX, rebalanceo de cartera: si en el mes la bolsa de EE. UU. le ganó a la local, los inversionistas
      extranjeros quedan con demasiados dólares y venden USD al cierre de mes para volver a su peso objetivo.
      Señal al cierre del 3.er día hábil antes de fin de mes; posición hasta el cierre del último día hábil.
      EURUSD con DAX, GBPUSD con FTSE, USDJPY con Nikkei (USD es la moneda base: el signo se invierte).
"""
import pandas as pd

import lab

INDICES = ["SPX", "NDX", "DJI", "DAX", "N225", "FTSE"]
FX_PAIRS = {"EURUSD": ("DAX", 1), "GBPUSD": ("FTSE", 1), "USDJPY": ("N225", -1)}


def trading_day_ranks(index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """Número de día hábil desde el inicio del mes (1, 2, ...) y hasta el final (1 = último)."""
    month = pd.Series(index.to_period("M"), index=index)
    from_start = month.groupby(month).cumcount() + 1
    from_end = month.groupby(month).cumcount(ascending=False) + 1
    return from_start, from_end


def turn_of_month_position(close: pd.Series, last_days: int, first_days: int) -> pd.Series:
    """Largo en los cierres desde el día -last_days hasta el día first_days-1 del mes nuevo.

    La posición fijada al cierre de t gana t -> t+1, así que se capturan los días -(last_days-1)..-1 y +1..+first_days.
    """
    start, end = trading_day_ranks(close.index)
    return ((end <= last_days) | (start < first_days)).astype(float)


def rebalancing_position(fx_close: pd.Series, local_index: str, usd_sign: int) -> pd.Series:
    spx = lab.load("SPX").close.reindex(fx_close.index, method="ffill")
    local = lab.load(local_index).close.reindex(fx_close.index, method="ffill")
    month = pd.Series(fx_close.index.to_period("M"), index=fx_close.index)
    us_mtd = spx / spx.groupby(month).transform("first") - 1
    local_mtd = local / local.groupby(month).transform("first") - 1
    _, end = trading_day_ranks(fx_close.index)
    # Señal en el cierre del día -3, se mantiene en -3 y -2 (gana los días -2 y -1).
    signal_day = end == 3
    direction = (us_mtd - local_mtd).where(signal_day).apply(lambda x: 1.0 if x > 0 else (-1.0 if x < 0 else 0.0))
    direction = direction.where(signal_day).ffill().where(end.isin([3, 2])).fillna(0)
    return direction * usd_sign  # vender USD = comprar EURUSD/GBPUSD = vender USDJPY


def evaluate(hypothesis, variant, name, position, close):
    daily = lab.in_period(lab.strategy_returns(position, close, name), "exploracion")
    result = lab.stats(daily)
    p = lab.null_pvalue(position, close, name, "exploracion")
    trials = lab.register(hypothesis, f"{variant} {name}", "exploracion", result, p)
    return result, p, trials


if __name__ == "__main__":
    for variant, (last_days, first_days) in {"H01a [-2,+3]": (2, 3), "H01b [-1,+4]": (1, 4)}.items():
        print(f"\n{variant}  (índices, solo compras)")
        for name in INDICES:
            close = lab.load(name).close
            result, p, trials = evaluate("H01 cambio de mes", variant, name, turn_of_month_position(close, last_days, first_days), close)
            print(f"  {name:5} {result} p_azar={p:.4f}")
    print("\nH01c rebalanceo FX de fin de mes")
    for pair, (local, sign) in FX_PAIRS.items():
        close = lab.load(pair).close
        result, p, trials = evaluate("H01 rebalanceo FX", "H01c", pair, rebalancing_position(close, local, sign), close)
        print(f"  {pair} vs {local:4} {result} p_azar={p:.4f}")
    print(f"\nPruebas en el registro: {trials}. Barra corregida (Bonferroni, alfa 5 %): p < {lab.required_p(trials):.4f}")
