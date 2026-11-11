// Réplica en TypeScript de core/risk.py y core/sizing.py, con los límites de config/settings.toml.
// Si cambian las reglas del bot, cambiarlas aquí también: la interfaz debe decir lo mismo que el código.

export const LIMITS = {
  riskPerTradePct: 0.5,
  maxDailyLossPct: 2.0,
  maxTradesPerDay: 3,
  maxOpenPositions: 2,
  maxSpreadPoints: 20,
  minRewardRisk: 1.0,
  tradingStart: '08:00',
  tradingEnd: '15:59',
  fridayClose: '20:00',
};

export type RiskInput = {
  equity: number;
  balanceStartOfDay: number;
  pnlToday: number;
  riskMoney: number;
  lots: number;
  tradesToday: number;
  openPositions: number;
  spreadPoints: number;
  rewardRisk: number;
  weekday: number; // 0 = lunes … 6 = domingo, como Python
  time: string; // "HH:MM"
};

const money = (v: number) => v.toLocaleString('es', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Igual que evaluate(): devuelve TODAS las razones de bloqueo, no solo la primera. */
export function evaluate(s: RiskInput, l = LIMITS): string[] {
  const reasons: string[] = [];
  const dailyLimit = (s.balanceStartOfDay * l.maxDailyLossPct) / 100;
  const maxRisk = (s.equity * l.riskPerTradePct) / 100;

  if (s.lots <= 0) reasons.push('el lote mínimo arriesga más que el riesgo permitido');
  if (s.riskMoney > maxRisk * 1.0001) reasons.push(`riesgo ${money(s.riskMoney)} supera el máximo por operación ${money(maxRisk)}`);
  if (-s.pnlToday + s.riskMoney > dailyLimit)
    reasons.push(`con esta operación la pérdida del día podría llegar a ${money(-s.pnlToday + s.riskMoney)}, límite ${money(dailyLimit)}`);
  if (s.tradesToday >= l.maxTradesPerDay) reasons.push(`ya hay ${s.tradesToday} operaciones hoy (máximo ${l.maxTradesPerDay})`);
  if (s.openPositions >= l.maxOpenPositions) reasons.push(`${s.openPositions} posiciones abiertas (máximo ${l.maxOpenPositions})`);
  if (s.spreadPoints > l.maxSpreadPoints) reasons.push(`spread ${s.spreadPoints} puntos (máximo ${l.maxSpreadPoints})`);
  if (s.rewardRisk < l.minRewardRisk) reasons.push(`beneficio/riesgo ${s.rewardRisk.toFixed(2)} menor a ${l.minRewardRisk}`);
  if (!(l.tradingStart <= s.time && s.time <= l.tradingEnd)) reasons.push(`${s.time} fuera del horario ${l.tradingStart}-${l.tradingEnd}`);
  const FRIDAY = 4;
  if (l.fridayClose && (s.weekday > FRIDAY || (s.weekday === FRIDAY && s.time >= l.fridayClose)))
    reasons.push(`viernes desde ${l.fridayClose} o fin de semana: no se abren posiciones`);
  return reasons;
}

export type SymbolSpec = { tickSize: number; tickValue: number; volumeStep: number; volumeMin: number; volumeMax: number };

/** EURUSD típico en una cuenta en USD: 1 lote, 1 pip (0.0001) = USD 10. */
export const EURUSD: SymbolSpec = { tickSize: 0.00001, tickValue: 1, volumeStep: 0.01, volumeMin: 0.01, volumeMax: 100 };

export const lossPerLot = (entry: number, stop: number, spec: SymbolSpec) => (Math.abs(entry - stop) / spec.tickSize) * spec.tickValue;

/** Igual que lots_for_risk(): redondea HACIA ABAJO; si ni el lote mínimo cabe, devuelve 0. */
export function lotsForRisk(riskMoney: number, entry: number, stop: number, spec: SymbolSpec): number {
  const perLot = lossPerLot(entry, stop, spec);
  if (perLot <= 0) return 0;
  const steps = Math.floor(Number((riskMoney / perLot / spec.volumeStep).toFixed(9)));
  const lots = Math.min(steps * spec.volumeStep, spec.volumeMax);
  return lots < spec.volumeMin ? 0 : Number(lots.toFixed(8));
}
