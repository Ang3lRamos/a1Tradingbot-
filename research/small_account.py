"""¿Qué pasa con una cuenta pequeña? Simulación de cartera con un solo saldo compartido.

Toma las operaciones del backtest del bot (señales, costos y swap reales) y las vuelve a dimensionar sobre un saldo
común, en orden de fecha: lote = riesgo del saldo actual / riesgo por lote, redondeado hacia abajo a 0.01.
Si ni el lote mínimo cabe, la operación se salta. Respeta el máximo de posiciones abiertas de cada bot.
El resultado de cada operación escala con los lotes (incluidos comisión y swap, que son por lote).
"""
import math
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mt5bot.backtest.simulator import run_backtest  # noqa: E402
from mt5bot.config import load_settings  # noqa: E402
from mt5bot.io.history_files import load_bars, load_spec  # noqa: E402

BOTS = {"Donchian": (ROOT / "config/settings.toml", "H4"), "RSI2": (ROOT / "config/rsi2.toml", "D1")}
LOT_STEP, MIN_LOT = 0.01, 0.01


def all_trades(config: Path, timeframe: str):
    """Operaciones del backtest con saldo grande (ninguna bloqueada por lote mínimo)."""
    settings = load_settings(config)
    settings = replace(settings, backtest=replace(settings.backtest, initial_balance=10_000_000))
    trades = []
    for symbol in settings.bot.symbols:
        bars = load_bars(ROOT / "data" / f"{symbol}_{timeframe}.csv")
        spec = load_spec(ROOT / "data" / f"{symbol}_spec.json")
        trades += [(symbol, t) for t in run_backtest(symbol, bars, spec, settings).trades]
    return settings, sorted(trades, key=lambda st: st[1].entry_time)


def simulate(trades, start_balance: float, risk_pct: float, max_open: int) -> dict:
    balance, peak, worst_dd = start_balance, start_balance, 0.0
    open_until: list[pd.Timestamp] = []
    taken, skipped_lot, skipped_slots, risks = 0, 0, 0, []
    for symbol, t in trades:
        open_until = [end for end in open_until if end > t.entry_time]
        if len(open_until) >= max_open:
            skipped_slots += 1
            continue
        risk_per_lot = t.risk_money / t.lots
        lots = math.floor(round(balance * risk_pct / 100 / risk_per_lot / LOT_STEP, 9)) * LOT_STEP
        if lots < MIN_LOT:
            skipped_lot += 1
            continue
        pnl = t.pnl / t.lots * lots
        risks.append(100 * lots * risk_per_lot / balance)
        balance += pnl
        taken += 1
        open_until.append(t.exit_time)
        peak = max(peak, balance)
        worst_dd = max(worst_dd, (peak - balance) / peak)
        if balance <= 0:
            break
    return {"ops": taken, "salta_lote": skipped_lot, "salta_cupo": skipped_slots, "final": balance,
            "peor_caida_pct": 100 * worst_dd, "riesgo_real_pct": sum(risks) / len(risks) if risks else None}


if __name__ == "__main__":
    for name, (config, timeframe) in BOTS.items():
        settings, trades = all_trades(config, timeframe)
        print(f"\n{name}: {len(trades)} operaciones en el backtest, máximo {settings.risk.max_open_positions} abiertas a la vez")
        for balance in (100, 1_000, 10_000):
            for risk in (0.5, 2, 5, 10):
                r = simulate(trades, balance, risk, settings.risk.max_open_positions)
                real = "—" if r["riesgo_real_pct"] is None else f"{r['riesgo_real_pct']:.1f} %"
                print(f"  USD {balance:>6,} riesgo {risk:>4} % -> {r['ops']:4} ops (saltadas por lote {r['salta_lote']:4}) | "
                      f"riesgo real {real:>6} | final USD {r['final']:>10,.2f} ({100 * (r['final'] / balance - 1):+6.1f} %) | "
                      f"peor caída {r['peor_caida_pct']:5.1f} %")
