"""RSI2 sobre ETF (SPY, QQQ, DIA) con el simulador del bot y la configuración de Alpaca (config/alpaca_rsi2.toml).

Mismo código que corre el bot: señal al cierre, entrada a la apertura siguiente, salida por regla a la apertura
siguiente, stop de emergencia de 3 ATR, lotes = acciones enteras por riesgo (0.5 %), sin comisión ni swap.
Datos diarios de Yahoo desde 2010 (precios sin ajustar por dividendos). Da los expected_* del panel.
"""
import sys
from pathlib import Path

import pandas as pd

import lab

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mt5bot.backtest.simulator import run_backtest  # noqa: E402
from mt5bot.config import load_settings  # noqa: E402
from mt5bot.core.models import SymbolSpec  # noqa: E402

START = "2010-01-01"


def bars_for(name: str) -> pd.DataFrame:
    bars = lab.load(name).reset_index()
    bars = bars[bars["time"] >= START].copy()
    bars["tick_volume"], bars["spread"] = 0, 1
    return bars.reset_index(drop=True)


def stock_spec(name: str) -> SymbolSpec:
    return SymbolSpec(name=name, digits=2, point=0.01, tick_size=0.01, tick_value=0.01,
                      volume_min=1, volume_max=100_000, volume_step=1)


if __name__ == "__main__":
    settings = load_settings(ROOT / "config/alpaca_rsi2.toml")
    rows = []
    for name in settings.bot.symbols:
        result = run_backtest(name, bars_for(name), stock_spec(name), settings)
        rows += [{"symbol": name, "entry": t.entry_time, "r": t.r, "pnl": t.pnl} for t in result.trades]
    trades = pd.DataFrame(rows)
    trades["period"] = pd.cut(trades["entry"], pd.to_datetime(["2000-01-01", "2017-01-01", "2022-01-01", "2100-01-01"]),
                              labels=["2010-2016", "2017-2021", "2022+"], right=False)
    months = (trades["entry"].max() - trades["entry"].min()).days / 30.44
    print(f"total: {len(trades)} ops | ganadoras {100 * (trades.r > 0).mean():.1f} % | media {trades.r.mean():+.3f} R | "
          f"{len(trades) / months:.1f} ops/mes | resultado USD {trades.pnl.sum():,.0f}")
    for (group, label), part in [*(((g, "símbolo"), p) for g, p in trades.groupby("symbol")),
                                 *(((g, "periodo"), p) for g, p in trades.groupby("period", observed=True))]:
        print(f"  {label} {group:10} {len(part):4} ops | ganadoras {100 * (part.r > 0).mean():5.1f} % | "
              f"media {part.r.mean():+.3f} R")
