import tomllib
from dataclasses import dataclass
from datetime import time
from pathlib import Path

STRATEGY_NAMES = ("orb", "donchian", "rsi2")
BROKERS = ("mt5", "alpaca", "alpaca_crypto")


@dataclass(frozen=True)
class BotConfig:
    broker: str
    mode: str
    allow_real_account: bool
    symbols: list[str]
    timeframe: str
    magic: int
    max_entry_delay_minutes: int
    journal_path: Path
    kill_switch_file: Path
    fractional: bool  # solo Alpaca: acciones fraccionadas, stop DAY que el bot renueva cada sesión


@dataclass(frozen=True)
class OrbConfig:
    range_start: time
    range_end: time
    entry_until: time
    stop_mode: str


@dataclass(frozen=True)
class DonchianConfig:
    channel_bars: int
    trend_ema: int
    stop_atr: float


@dataclass(frozen=True)
class Rsi2Config:
    rsi_period: int
    entry_below: float
    trend_sma: int
    exit_sma: int
    stop_atr: float
    max_bars: int
    weekends: bool = False  # cripto: sábado y domingo son días normales; en CFD solo hay la vela corta del domingo


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    target_r: float
    breakeven_at_r: float
    trail_atr: float
    atr_period: int
    flat_by: time | None
    orb: OrbConfig
    donchian: DonchianConfig
    rsi2: Rsi2Config


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade_pct: float
    max_daily_loss_pct: float
    max_trades_per_day: int
    max_open_positions: int
    max_spread_points: int
    min_reward_risk: float
    trading_start: time
    trading_end: time
    friday_close: time | None


@dataclass(frozen=True)
class BacktestConfig:
    initial_balance: float
    spread_points: int
    commission_per_lot: float
    monte_carlo_runs: int
    seed: int
    # Resultado del backtest, para comparar contra la demo en el panel.
    expected_win_rate_pct: float
    expected_avg_r: float
    expected_trades_per_month: float


@dataclass(frozen=True)
class Settings:
    bot: BotConfig
    strategy: StrategyConfig
    risk: RiskLimits
    backtest: BacktestConfig


def _hhmm(value: str) -> time:
    return time.fromisoformat(value)


def _optional_hhmm(value: str) -> time | None:
    return _hhmm(value) if value else None


def _strategy(raw: dict) -> StrategyConfig:
    if raw["name"] not in STRATEGY_NAMES:
        raise ValueError(f"strategy.name debe ser uno de {STRATEGY_NAMES}, no {raw['name']!r}")
    orb, donchian = raw["orb"], raw["donchian"]
    if orb["stop_mode"] not in ("range_mid", "range_opposite"):
        raise ValueError(f"strategy.orb.stop_mode no válido: {orb['stop_mode']!r}")
    return StrategyConfig(
        name=raw["name"],
        target_r=raw["target_r"],
        breakeven_at_r=raw["breakeven_at_r"],
        trail_atr=raw["trail_atr"],
        atr_period=raw["atr_period"],
        flat_by=_optional_hhmm(raw["flat_by"]),
        orb=OrbConfig(range_start=_hhmm(orb["range_start"]), range_end=_hhmm(orb["range_end"]),
                      entry_until=_hhmm(orb["entry_until"]), stop_mode=orb["stop_mode"]),
        donchian=DonchianConfig(**donchian),
        rsi2=Rsi2Config(**raw["rsi2"]),
    )


def load_settings(path: Path) -> Settings:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    bot, risk = raw["bot"], raw["risk"]

    if bot["mode"] not in ("dry_run", "live"):
        raise ValueError(f"bot.mode debe ser 'dry_run' o 'live', no {bot['mode']!r}")
    if bot["broker"] not in BROKERS:
        raise ValueError(f"bot.broker debe ser uno de {BROKERS}, no {bot['broker']!r}")

    start, end = risk["trading_hours"]
    return Settings(
        bot=BotConfig(
            broker=bot["broker"],
            mode=bot["mode"],
            allow_real_account=bot["allow_real_account"],
            symbols=bot["symbols"],
            timeframe=bot["timeframe"],
            magic=bot["magic"],
            max_entry_delay_minutes=bot["max_entry_delay_minutes"],
            journal_path=Path(bot["journal_path"]).expanduser(),
            kill_switch_file=Path(bot["kill_switch_file"]),
            fractional=bot.get("fractional", False),
        ),
        strategy=_strategy(raw["strategy"]),
        risk=RiskLimits(
            risk_per_trade_pct=risk["risk_per_trade_pct"],
            max_daily_loss_pct=risk["max_daily_loss_pct"],
            max_trades_per_day=risk["max_trades_per_day"],
            max_open_positions=risk["max_open_positions"],
            max_spread_points=risk["max_spread_points"],
            min_reward_risk=risk["min_reward_risk"],
            trading_start=_hhmm(start),
            trading_end=_hhmm(end),
            friday_close=_optional_hhmm(risk["friday_close"]),
        ),
        backtest=BacktestConfig(**raw["backtest"]),
    )
