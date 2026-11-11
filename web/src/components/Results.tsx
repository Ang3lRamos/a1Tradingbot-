// Resultados de backtest con costos, tomados de CLAUDE.md ("Estado actual" y "Bots en la demo").
const RESULTS = [
  { name: 'RSI2 en ETFs (SPY, QQQ, DIA)', period: 'Yahoo 2010–2026', trades: 467, value: '+0,112 R', win: '70,9 %', verdict: 'Con ventaja', tone: 'up' },
  { name: 'Donchian H4 en 11 símbolos', period: 'Broker 2025–2026', trades: 516, value: '−0,035 R', win: '—', verdict: 'Sin ventaja probada', tone: 'warn' },
  { name: 'RSI2 cripto (BTC, ETH, SOL)', period: '2021–2026', trades: 126, value: '≈ 0 R', win: '—', verdict: 'Prueba técnica', tone: 'muted' },
  { name: 'ORB en EURUSD M15', period: 'Broker 2025', trades: null, value: 'PF 0,72', win: '—', verdict: 'Descartada', tone: 'down' },
];

const COLOR: Record<string, string> = { up: 'var(--up)', warn: 'var(--warn)', muted: 'var(--text-3)', down: 'var(--down)' };

export default function Results() {
  return (
    <section id="resultados">
      <div className="section-head">
        <p className="eyebrow">05 · Resultados</p>
        <h2>Lo que dicen los backtests, sin maquillaje</h2>
        <p>Con spread, comisión de USD 10 por lote y swap. Si una vela toca stop y objetivo, cuenta el stop. Por eso el resultado real suele ser igual o peor.</p>
      </div>
      <div className="card table-wrap">
        <table>
          <thead>
            <tr><th>Estrategia</th><th>Datos</th><th className="num">Operaciones</th><th className="num">Promedio</th><th className="num">Ganadoras</th><th>Veredicto</th></tr>
          </thead>
          <tbody>
            {RESULTS.map((r) => (
              <tr key={r.name}>
                <td><strong>{r.name}</strong></td>
                <td className="muted">{r.period}</td>
                <td className="num mono">{r.trades ?? '—'}</td>
                <td className="num mono" style={{ color: COLOR[r.tone] }}>{r.value}</td>
                <td className="num mono">{r.win}</td>
                <td><span className="pill" style={{ color: COLOR[r.tone] }}><span className="dot" /> {r.verdict}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">R = resultado en múltiplos de lo arriesgado por operación. PF = profit factor (ganancias brutas / pérdidas brutas).</p>
    </section>
  );
}
