import { useState } from 'react';
import { EURUSD, evaluate, LIMITS, lossPerLot, lotsForRisk } from '../lib/rules';

const DAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const fmt = (v: number, d = 2) => v.toLocaleString('es', { minimumFractionDigits: d, maximumFractionDigits: d });

export default function Simulators() {
  // Cuenta y operación propuestas (valores iniciales que pasan el filtro).
  const [equity, setEquity] = useState(100000);
  const [pnlToday, setPnlToday] = useState(-300);
  const [stopPips, setStopPips] = useState(25);
  const [rr, setRr] = useState(2);
  const [tradesToday, setTradesToday] = useState(1);
  const [openPositions, setOpenPositions] = useState(0);
  const [spread, setSpread] = useState(8);
  const [weekday, setWeekday] = useState(2);
  const [time, setTime] = useState('10:00');

  const entry = 1.085;
  const stop = entry - stopPips * 0.0001;
  const riskBudget = (equity * LIMITS.riskPerTradePct) / 100;
  const lots = lotsForRisk(riskBudget, entry, stop, EURUSD);
  const riskMoney = lots * lossPerLot(entry, stop, EURUSD);
  const reasons = evaluate({
    equity, balanceStartOfDay: equity - pnlToday, pnlToday, riskMoney, lots,
    tradesToday, openPositions, spreadPoints: spread, rewardRisk: rr, weekday, time,
  });
  const passed = reasons.length === 0;

  return (
    <section id="simulador">
      <div className="section-head">
        <p className="eyebrow">03 · Simulador</p>
        <h2>Prueba el filtro de riesgo</h2>
        <p>
          Estas son las reglas reales del bot, traducidas tal cual desde <code className="mono">core/risk.py</code> y{' '}
          <code className="mono">core/sizing.py</code>. Cambia la situación y mira si la orden pasa.
        </p>
      </div>

      <div className="sim">
        <div className="card sim-form">
          <h3 className="h3">Cuenta</h3>
          <Field label="Capital (USD)" value={equity} onChange={setEquity} step={1000} min={100} />
          <Field label="Resultado de hoy (USD)" value={pnlToday} onChange={setPnlToday} step={100} />
          <Field label="Operaciones hoy" value={tradesToday} onChange={setTradesToday} min={0} />
          <Field label="Posiciones abiertas" value={openPositions} onChange={setOpenPositions} min={0} />

          <h3 className="h3 sim-sub">Orden en EURUSD</h3>
          <Field label="Stop (pips)" value={stopPips} onChange={setStopPips} min={1} />
          <Field label="Beneficio / riesgo" value={rr} onChange={setRr} step={0.1} min={0} />
          <Field label="Spread (puntos)" value={spread} onChange={setSpread} min={0} />
          <div className="field-row">
            <label className="field">
              <span>Día</span>
              <select value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>
                {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
              </select>
            </label>
            <label className="field">
              <span>Hora del servidor</span>
              <input type="time" value={time} onChange={(e) => setTime(e.target.value || '00:00')} />
            </label>
          </div>
        </div>

        <div className="sim-out">
          <div className={`card verdict ${passed ? 'pass' : 'block'}`} aria-live="polite">
            <span className="verdict-tag mono">{passed ? 'PASS' : 'BLOCK'}</span>
            <p className="verdict-text">{passed ? 'La orden cumple todos los límites y se enviaría con stop y objetivo dentro.' : 'La orden no sale. Estas son todas las razones:'}</p>
            {!passed && (
              <ul className="reasons">
                {reasons.map((r) => <li key={r}>{r}</li>)}
              </ul>
            )}
          </div>

          <div className="card">
            <h3 className="h3">Cálculo de lotes</h3>
            <dl className="calc">
              <dt>Riesgo permitido ({fmt(LIMITS.riskPerTradePct, 1)} %)</dt><dd className="mono">USD {fmt(riskBudget)}</dd>
              <dt>Pérdida por lote en el stop</dt><dd className="mono">USD {fmt(lossPerLot(entry, stop, EURUSD))}</dd>
              <dt>Lotes (redondeo hacia abajo)</dt><dd className="mono">{fmt(lots)}</dd>
              <dt>Riesgo real</dt><dd className="mono">USD {fmt(riskMoney)}</dd>
            </dl>
            <p className="note">Nunca arriesga más de lo pedido: si ni 0,01 lotes caben, no opera.</p>
          </div>

          <div className="card limits">
            <h3 className="h3">Límites configurados</h3>
            <ul>
              <li>Pérdida diaria máxima <b className="mono">{LIMITS.maxDailyLossPct} %</b> (incluye lo flotante)</li>
              <li>Operaciones por día <b className="mono">{LIMITS.maxTradesPerDay}</b> · posiciones a la vez <b className="mono">{LIMITS.maxOpenPositions}</b></li>
              <li>Spread máximo <b className="mono">{LIMITS.maxSpreadPoints}</b> puntos · beneficio/riesgo mínimo <b className="mono">{LIMITS.minRewardRisk}</b></li>
              <li>Horario <b className="mono">{LIMITS.tradingStart}–{LIMITS.tradingEnd}</b> · viernes hasta las <b className="mono">{LIMITS.fridayClose}</b></li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function Field({ label, value, onChange, step = 1, min }: { label: string; value: number; onChange: (v: number) => void; step?: number; min?: number }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type="number" value={value} step={step} min={min} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}
