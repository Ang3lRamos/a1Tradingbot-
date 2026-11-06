import math

from mt5bot.core.models import SymbolSpec


def loss_per_lot(entry: float, stop: float, spec: SymbolSpec) -> float:
    """Dinero que pierde 1 lote si el precio va de entry a stop, en moneda de la cuenta."""
    ticks = abs(entry - stop) / spec.tick_size
    return ticks * spec.tick_value


def lots_for_risk(risk_money: float, entry: float, stop: float, spec: SymbolSpec) -> float:
    """Lotes máximos que no superan risk_money en el stop. Devuelve 0 si ni el lote mínimo cabe.

    Redondea hacia abajo al volume_step: nunca arriesgar más de lo pedido.
    """
    per_lot = loss_per_lot(entry, stop, spec)
    if per_lot <= 0:
        raise ValueError("entry y stop no pueden ser iguales")

    steps = math.floor(round(risk_money / per_lot / spec.volume_step, 9))
    lots = min(steps * spec.volume_step, spec.volume_max)
    if lots < spec.volume_min:
        return 0.0
    return round(lots, 8)
