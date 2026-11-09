"""H07: RSI2 y Donchian diarios en cripto de Alpaca (BTC, ETH, SOL), solo compras (Alpaca no permite cortos en cripto).

Simulador del bot con la configuración de config/alpaca_rsi2.toml (24/7, sin cierre del viernes). Costos de Alpaca
nivel 1: comisión 0.25 % por lado (taker, se resta del resultado de cada operación) y spread de ~3 pb (medido:
BTC/USD 19 USD sobre 74.900). Sin swap: es cripto al contado. Datos diarios de Alpaca (velas UTC) desde 2021,
en caché en ~/.mt5bot/research_data/. Exploración 2021–2023, validación 2024+.
"""
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pandas as pd

import lab

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mt5bot.backtest.simulator import run_backtest  # noqa: E402
from mt5bot.config import load_settings  # noqa: E402
from mt5bot.core.models import SymbolSpec  # noqa: E402

SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"]
FEE = 0.0025
SPREAD = 0.0003
POINT = 0.01
SPLIT = pd.Timestamp("2024-01-01")


def crypto_bars(symbol: str) -> pd.DataFrame:
    path = lab.DATA_DIR / f"alpaca_{symbol.replace('/', '')}_D1.csv"
    if not path.exists():
        from alpaca.data.historical import CryptoHistoricalDataClient
        from alpaca.data.requests import CryptoBarsRequest
        from alpaca.data.timeframe import TimeFrame
        request = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=datetime(2020, 1, 1))
        frame = CryptoHistoricalDataClient().get_crypto_bars(request).df.loc[symbol].reset_index()
        frame = frame.rename(columns={"timestamp": "time"})[["time", "open", "high", "low", "close"]]
        frame["time"] = frame["time"].dt.tz_localize(None)
        frame = frame[frame["time"] < pd.Timestamp.now().normalize()]  # sin la vela de hoy, que sigue abierta
        frame.to_csv(path, index=False)
    bars = pd.read_csv(path, parse_dates=["time"])
    bars["tick_volume"], bars["spread"] = 0, (bars["close"] * SPREAD / POINT).round().astype(int)
    return bars


def spec(symbol: str) -> SymbolSpec:
    return SymbolSpec(name=symbol, digits=2, point=POINT, tick_size=POINT, tick_value=POINT,
                      volume_min=1e-9, volume_max=1e9, volume_step=1e-9)


def trades_for(strategy: str) -> pd.DataFrame:
    settings = load_settings(ROOT / "config/alpaca_rsi2.toml")
    rsi2 = replace(settings.strategy.rsi2, weekends=True)
    settings = replace(settings, strategy=replace(settings.strategy, name=strategy, rsi2=rsi2),
                       risk=replace(settings.risk, max_spread_points=10**9))
    rows = []
    for symbol in SYMBOLS:
        for t in run_backtest(symbol, crypto_bars(symbol), spec(symbol), settings).trades:
            if t.side != "buy":
                continue
            fee = FEE * (t.entry + t.exit_price) * t.lots
            rows.append({"symbol": symbol, "entry": t.entry_time, "r": (t.pnl - fee) / t.risk_money,
                         "r_sin_comision": t.r})
    return pd.DataFrame(rows)


def summary(part: pd.DataFrame) -> dict:
    r = part["r"]
    return {"n": len(r), "gana_pct": round(100 * (r > 0).mean(), 1), "avg_r": round(r.mean(), 3),
            "t": round(r.mean() / r.std() * len(r) ** 0.5, 2) if len(r) > 1 else None,
            "avg_r_sin_comision": round(part["r_sin_comision"].mean(), 3)}


if __name__ == "__main__":
    for strategy in ("rsi2", "donchian"):
        trades = trades_for(strategy)
        for period, part in (("exploracion_2021_2023", trades[trades.entry < SPLIT]),
                             ("validacion_2024", trades[trades.entry >= SPLIT])):
            result = summary(part)
            lab.register("H07 cripto Alpaca", f"H07 {strategy} D1 compras BTC+ETH+SOL", period, result, None)
            print(f"{strategy:9} {period:22} {result}")
        for symbol, part in trades.groupby("symbol"):
            print(f"    {symbol:8} {summary(part)}")
