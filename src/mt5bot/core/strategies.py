from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from mt5bot.config import StrategyConfig
from mt5bot.core import strategy_donchian, strategy_orb, strategy_rsi2
from mt5bot.core.models import Signal


@dataclass(frozen=True)
class Strategy:
    find_signal: Callable[[str, pd.DataFrame, StrategyConfig], Signal | None]
    bars_needed: Callable[[StrategyConfig], int]
    # Salida por regla al cierre de cada vela (además de stop, target y cierres forzados); None si no tiene.
    exit_due: Callable[[pd.DataFrame, datetime, StrategyConfig], bool] | None = None


_STRATEGIES = {
    "orb": Strategy(strategy_orb.find_signal, strategy_orb.bars_needed),
    "donchian": Strategy(strategy_donchian.find_signal, strategy_donchian.bars_needed),
    "rsi2": Strategy(strategy_rsi2.find_signal, strategy_rsi2.bars_needed, strategy_rsi2.exit_due),
}


def get_strategy(name: str) -> Strategy:
    return _STRATEGIES[name]
