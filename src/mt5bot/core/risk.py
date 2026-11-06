from mt5bot.config import RiskLimits
from mt5bot.core.models import OrderPlan, RiskDecision, RiskState
from mt5bot.core.position_rules import FRIDAY


def evaluate(plan: OrderPlan, state: RiskState, limits: RiskLimits) -> RiskDecision:
    """Aplica todos los límites y devuelve todas las razones de bloqueo, no solo la primera."""
    reasons = []
    daily_limit = state.balance_start_of_day * limits.max_daily_loss_pct / 100
    max_risk = state.equity * limits.risk_per_trade_pct / 100
    hour = state.now.time()

    if plan.lots <= 0:
        reasons.append("el lote mínimo arriesga más que el riesgo permitido")
    if plan.risk_money > max_risk * 1.0001:
        reasons.append(f"riesgo {plan.risk_money:.2f} supera el máximo por operación {max_risk:.2f}")
    if -state.pnl_today + plan.risk_money > daily_limit:
        reasons.append(
            f"con esta operación la pérdida del día podría llegar a "
            f"{-state.pnl_today + plan.risk_money:.2f}, límite {daily_limit:.2f}"
        )
    if state.trades_today >= limits.max_trades_per_day:
        reasons.append(f"ya hay {state.trades_today} operaciones hoy (máximo {limits.max_trades_per_day})")
    if state.open_positions >= limits.max_open_positions:
        reasons.append(f"{state.open_positions} posiciones abiertas (máximo {limits.max_open_positions})")
    if state.spread_points > limits.max_spread_points:
        reasons.append(f"spread {state.spread_points} puntos (máximo {limits.max_spread_points})")
    if plan.signal.reward_risk < limits.min_reward_risk:
        reasons.append(f"beneficio/riesgo {plan.signal.reward_risk:.2f} menor a {limits.min_reward_risk}")
    if not limits.trading_start <= hour <= limits.trading_end:
        reasons.append(f"{hour:%H:%M} fuera del horario {limits.trading_start:%H:%M}-{limits.trading_end:%H:%M}")
    friday = limits.friday_close
    if friday is not None and (state.now.weekday() > FRIDAY or (state.now.weekday() == FRIDAY and hour >= friday)):
        reasons.append(f"viernes desde {friday:%H:%M} o fin de semana: no se abren posiciones")

    return RiskDecision(passed=not reasons, reasons=reasons)
