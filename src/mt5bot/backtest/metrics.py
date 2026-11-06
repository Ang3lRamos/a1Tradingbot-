import numpy as np

from mt5bot.backtest.simulator import Trade


def summarize(trades: list[Trade], initial_balance: float) -> dict:
    if not trades:
        return {"trades": 0}
    pnl = np.array([t.pnl for t in trades])
    r = np.array([t.r for t in trades])
    equity = initial_balance + np.cumsum(pnl)
    peaks = np.maximum.accumulate(np.concatenate([[initial_balance], equity]))[1:]
    gains, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    return {
        "trades": len(trades),
        "win_rate_pct": round(100 * (pnl > 0).mean(), 1),
        "avg_r": round(r.mean(), 3),
        "profit_factor": round(gains / losses, 2) if losses else float("inf"),
        "net_pnl": round(pnl.sum(), 2),
        "return_pct": round(100 * pnl.sum() / initial_balance, 2),
        "max_drawdown_pct": round(100 * ((peaks - equity) / peaks).max(), 2),
        "exits": {reason: sum(t.exit_reason == reason for t in trades)
                  for reason in sorted({t.exit_reason for t in trades})},
    }


def monte_carlo(r_values: list[float], risk_pct: float, runs: int, seed: int) -> dict:
    """Remuestrea los resultados en R (con reemplazo) para ver el rango de caminos posibles.

    El backtest es un solo orden de operaciones; aquí se ve qué tan distinto
    podría haber salido con las mismas operaciones en otro orden y proporción.
    """
    rng = np.random.default_rng(seed)
    samples = rng.choice(np.asarray(r_values), size=(runs, len(r_values)), replace=True)
    curves = np.cumprod(1 + samples * risk_pct / 100, axis=1)
    peaks = np.maximum.accumulate(np.hstack([np.ones((runs, 1)), curves]), axis=1)[:, 1:]
    drawdowns = ((peaks - curves) / peaks).max(axis=1) * 100
    returns = (curves[:, -1] - 1) * 100

    def pct(values, q):
        return round(float(np.percentile(values, q)), 2)

    return {
        "runs": runs,
        "return_pct": {"p5": pct(returns, 5), "p50": pct(returns, 50), "p95": pct(returns, 95)},
        "max_drawdown_pct": {"p50": pct(drawdowns, 50), "p95": pct(drawdowns, 95)},
        "prob_loss_pct": round(100 * float((returns < 0).mean()), 1),
        "prob_drawdown_over_20_pct": round(100 * float((drawdowns > 20).mean()), 1),
    }
