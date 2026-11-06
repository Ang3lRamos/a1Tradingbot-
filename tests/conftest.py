from dataclasses import replace
from datetime import datetime, time
from pathlib import Path

import pandas as pd
import pytest

from mt5bot.config import load_settings
from mt5bot.core.models import SymbolSpec

CONFIG = Path(__file__).parents[1] / "config" / "settings.toml"


@pytest.fixture
def settings():
    return load_settings(CONFIG)


@pytest.fixture
def orb_settings(settings):
    """ORB con los valores con que se escribieron sus tests, sin depender de la estrategia activa."""
    strategy = replace(settings.strategy, name="orb", target_r=1.5, breakeven_at_r=1.0, trail_atr=0,
                       flat_by=time(20, 0))
    return replace(settings, strategy=strategy, bot=replace(settings.bot, timeframe="M15"))


@pytest.fixture
def eurusd():
    # Cuenta en USD: 1 lote de EURUSD mueve 1 USD por tick de 0.00001 (10 USD por pip).
    return SymbolSpec(name="EURUSD", digits=5, point=0.00001, tick_size=0.00001, tick_value=1.0,
                      volume_min=0.01, volume_max=100.0, volume_step=0.01)


def make_bars(day: str, rows: list[tuple]) -> pd.DataFrame:
    """rows: (HH:MM, open, high, low, close)."""
    records = [{"time": datetime.fromisoformat(f"{day} {hhmm}"), "open": o, "high": h, "low": l, "close": c}
               for hhmm, o, h, l, c in rows]
    return pd.DataFrame(records)


def range_rows(high=1.1010, low=1.1000):
    """Cuatro velas M15 de 08:00 a 08:45 que forman el rango [low, high]."""
    mid = (high + low) / 2
    return [("08:00", mid, high, mid, mid), ("08:15", mid, mid, low, mid),
            ("08:30", mid, mid, mid, mid), ("08:45", mid, mid, mid, mid)]
