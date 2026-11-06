from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class SymbolSpec:
    """Lo que hace falta del symbol_info de MT5 para dimensionar una posición y estimar sus costos."""
    name: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    # Swap tal como lo da MT5; los valores por defecto (sin swap) son para especificaciones guardadas antes.
    contract_size: float = 1.0
    swap_long: float = 0.0
    swap_short: float = 0.0
    swap_mode: int = 0
    swap_triple_weekday: int = 2  # weekday() de Python en que se cobra triple (MT5 swap_rollover3days)


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str  # "buy" o "sell"
    bar_time: datetime
    entry: float
    stop: float
    target: float
    reason: str

    @property
    def direction(self) -> int:
        return 1 if self.side == "buy" else -1

    @property
    def reward_risk(self) -> float:
        return abs(self.target - self.entry) / abs(self.entry - self.stop)


@dataclass(frozen=True)
class OrderPlan:
    signal: Signal
    lots: float
    risk_money: float


@dataclass(frozen=True)
class RiskState:
    """Foto de la cuenta en el momento de decidir."""
    now: datetime
    balance_start_of_day: float
    equity: float
    pnl_today: float
    trades_today: int
    open_positions: int
    spread_points: int


@dataclass(frozen=True)
class RiskDecision:
    passed: bool
    reasons: list[str] = field(default_factory=list)
