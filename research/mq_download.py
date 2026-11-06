"""Descarga historia M15 larga del segundo terminal (MetaQuotes-Demo), un año por pedido.

Se conecta a la sesión abierta del terminal por su ruta, sin credenciales. Pide de a un año con pausas
para no saturar el terminal; si un año llega incompleto (el servidor aún lo está enviando), reintenta.
"""
import sys
import time
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

from lab import DATA_DIR

TERMINAL = r"C:\MT5_MetaQuotes\terminal64.exe"
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "JPN225", "DE40", "US500"]
FIRST_YEAR, PAUSE_SECONDS, RETRIES = 2005, 2, 4


def fetch_year(symbol: str, year: int) -> pd.DataFrame | None:
    start, end = datetime(year, 1, 1), datetime(year + 1, 1, 1)
    previous = -1
    for _ in range(RETRIES):
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, start, end)
        count = 0 if rates is None else len(rates)
        if count and count == previous:
            break  # dos respuestas iguales: el año ya está completo en el terminal
        previous = count
        time.sleep(PAUSE_SECONDS)
    if not previous:
        return None
    bars = pd.DataFrame(rates)
    bars["time"] = pd.to_datetime(bars["time"], unit="s")
    return bars[["time", "open", "high", "low", "close", "tick_volume", "spread"]]


def main(symbols: list[str]) -> None:
    if not mt5.initialize(path=TERMINAL, timeout=120000):
        raise SystemExit(f"no se pudo conectar al terminal de MetaQuotes: {mt5.last_error()}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for symbol in symbols:
            mt5.symbol_select(symbol, True)
            years = [y for y in range(FIRST_YEAR, datetime.now().year + 1)]
            parts = [part for y in years if (part := fetch_year(symbol, y)) is not None]
            if not parts:
                print(f"{symbol}: sin historia M15", flush=True)
                continue
            bars = pd.concat(parts).drop_duplicates("time").sort_values("time")
            bars.to_csv(DATA_DIR / f"mq_{symbol}_M15.csv", index=False)
            print(f"{symbol}: {len(bars):,} velas M15 desde {bars.time.min():%Y-%m-%d}", flush=True)
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main(sys.argv[1:] or SYMBOLS)
