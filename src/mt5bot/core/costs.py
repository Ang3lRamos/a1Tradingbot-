"""Costo de mantener una posición abierta de un día para otro (swap), con los datos del symbol_info de MT5."""
from datetime import datetime, timedelta

from mt5bot.core.models import SymbolSpec

SWAP_MODE_POINTS = 1
SWAP_MODES_PERCENT = (5, 6)  # % anual sobre el precio actual o el de apertura
SATURDAY = 5


def swap_per_night(spec: SymbolSpec, direction: int, price: float, lots: float) -> float:
    """Dinero que suma (positivo) o resta (negativo) una noche. Modos de swap no soportados cuentan como 0."""
    rate = spec.swap_long if direction == 1 else spec.swap_short
    if spec.swap_mode in SWAP_MODES_PERCENT:
        return rate / 100 / 360 * price * spec.contract_size * lots
    if spec.swap_mode == SWAP_MODE_POINTS:
        return rate * spec.point / spec.tick_size * spec.tick_value * lots
    return 0.0


def nights_charged(opened: datetime, closed: datetime, triple_weekday: int) -> int:
    """Noches de swap entre apertura y cierre: una por cada medianoche de día hábil, triple el día indicado."""
    nights, day = 0, opened.date()
    while day < closed.date():
        if day.weekday() < SATURDAY:
            nights += 3 if day.weekday() == triple_weekday else 1
        day += timedelta(days=1)
    return nights
