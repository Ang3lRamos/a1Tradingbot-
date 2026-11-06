from dataclasses import replace

from mt5bot.core.models import OrderPlan, Signal, SymbolSpec
from mt5bot.core.sizing import lots_for_risk, loss_per_lot


def plan_at_price(
    signal: Signal, fill_price: float, equity: float, risk_pct: float, spec: SymbolSpec, target_r: float
) -> OrderPlan | None:
    """Ajusta la señal al precio real de entrada y calcula lotes.

    La señal se generó al cierre de la vela; la orden se llena a otro precio
    (siguiente tick, spread). Se conserva el stop, se recalcula el target para
    mantener target_r y los lotes se calculan sobre la distancia real.
    Devuelve None si el precio ya pasó el stop.
    """
    risk_distance = (fill_price - signal.stop) * signal.direction
    if risk_distance <= 0:
        return None

    target = fill_price + target_r * risk_distance * signal.direction
    adjusted = replace(signal, entry=fill_price, target=target)
    lots = lots_for_risk(equity * risk_pct / 100, fill_price, signal.stop, spec)
    return OrderPlan(signal=adjusted, lots=lots, risk_money=lots * loss_per_lot(fill_price, signal.stop, spec))
