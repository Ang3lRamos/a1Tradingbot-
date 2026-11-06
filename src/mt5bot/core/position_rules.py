from datetime import datetime, time

FRIDAY = 4


def r_multiple(direction: int, entry: float, initial_stop: float, price: float) -> float:
    """Cuántas veces el riesgo inicial se ha ganado (positivo) o perdido (negativo)."""
    return (price - entry) * direction / ((entry - initial_stop) * direction)


def next_stop(direction: int, entry: float, initial_stop: float, current_stop: float, price: float,
              atr: float, at_r: float, trail_atr: float) -> float | None:
    """Nuevo stop si toca moverlo, o None.

    Desde at_r el stop pasa a la entrada (breakeven) y, con trail_atr > 0, sigue al
    precio a trail_atr x ATR. Solo se mueve a favor: nunca afloja la protección.
    """
    if at_r <= 0 or r_multiple(direction, entry, initial_stop, price) < at_r:
        return None
    candidate = entry
    if trail_atr > 0 and atr > 0:
        trail = price - direction * trail_atr * atr
        if (trail - candidate) * direction > 0:
            candidate = trail
    return candidate if (candidate - current_stop) * direction > 0 else None


def forced_close_reason(now: datetime, flat_by: time | None, friday_close: time | None) -> str | None:
    """Motivo para cerrar ya las posiciones (cierre diario o antes del fin de semana), o None.

    friday_close None: la estrategia mantiene posiciones durante el fin de semana.
    """
    if friday_close is not None and (now.weekday() > FRIDAY or (now.weekday() == FRIDAY and now.time() >= friday_close)):
        return "weekend"
    if flat_by is not None and now.time() >= flat_by:
        return "flat_by"
    return None
