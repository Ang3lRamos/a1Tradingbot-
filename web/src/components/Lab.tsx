import { useMemo, useState } from 'react';
import registry from '../research/registry.json';

type Row = { date: string; family: string; variant: string; period: string; p: number | null; sharpe?: number; ret_anual_pct?: number; peor_caida_pct?: number; avg_r?: number; n?: number };
const ROWS = registry as Row[];

// Barra del azar corregida por el número de pruebas (Bonferroni, como research/lab.py: required_p).
const REQUIRED_P = 0.05 / ROWS.length;
const FAMILIES = Array.from(new Set(ROWS.map((r) => r.family)));
const PERIOD_LABEL = (p: string) => p.replace(/_/g, ' ').replace('exploracion', 'exploración').replace('verificacion', 'verificación').replace('validacion', 'validación');

type SortKey = 'sharpe' | 'ret_anual_pct' | 'peor_caida_pct' | 'p';

export default function Lab() {
  const [family, setFamily] = useState('all');
  const [sort, setSort] = useState<SortKey>('p');
  const [all, setAll] = useState(false);

  const rows = useMemo(() => {
    const list = ROWS.filter((r) => family === 'all' || r.family === family);
    // El valor p va de menor a mayor; lo demás de mayor a menor (la peor caída menos severa es la más alta, −10 > −50).
    const asc = sort === 'p';
    const val = (r: Row) => (r[sort] ?? (asc ? Infinity : -Infinity)) as number;
    return [...list].sort((a, b) => (asc ? val(a) - val(b) : val(b) - val(a)));
  }, [family, sort]);

  const withP = ROWS.filter((r) => r.p != null);
  const nominal = withP.filter((r) => (r.p as number) < 0.05).length;
  const strict = withP.filter((r) => (r.p as number) <= REQUIRED_P).length;

  return (
    <section id="laboratorio">
      <div className="section-head">
        <p className="eyebrow">04 · Laboratorio</p>
        <h2>Cada idea se anota, incluso las que fallan</h2>
        <p>
          Toda prueba queda en <code className="mono">research/registry.csv</code>. El valor p mide qué tan seguido el azar
          (las mismas operaciones en fechas desplazadas) iguala el resultado. Con tantas pruebas, la barra se vuelve más exigente.
        </p>
      </div>

      <div className="grid-4 lab-kpis">
        <div className="card kpi"><span className="kpi-value mono">{ROWS.length}</span><span className="kpi-label">pruebas registradas</span></div>
        <div className="card kpi"><span className="kpi-value mono">{FAMILIES.length}</span><span className="kpi-label">familias de hipótesis</span></div>
        <div className="card kpi"><span className="kpi-value mono">{nominal}</span><span className="kpi-label">con p &lt; 0,05 (sin corregir)</span></div>
        <div className="card kpi"><span className="kpi-value mono">{strict}</span><span className="kpi-label">superan la barra corregida p ≤ {REQUIRED_P.toFixed(4)}</span></div>
      </div>

      <div className="card">
        <Scatter />
      </div>

      <div className="card lab-table">
        <div className="lab-tools">
          <label className="field inline">
            <span>Familia</span>
            <select value={family} onChange={(e) => setFamily(e.target.value)}>
              <option value="all">Todas ({ROWS.length})</option>
              {FAMILIES.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          <label className="field inline">
            <span>Ordenar por</span>
            <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
              <option value="p">Valor p (menor primero)</option>
              <option value="sharpe">Sharpe</option>
              <option value="ret_anual_pct">Retorno anual</option>
              <option value="peor_caida_pct">Peor caída (menor primero)</option>
            </select>
          </label>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Variante</th><th>Periodo</th><th className="num">Ret. anual</th><th className="num">Sharpe</th><th className="num">Peor caída</th><th className="num">p azar</th></tr>
            </thead>
            <tbody>
              {(all ? rows : rows.slice(0, 15)).map((r) => (
                <tr key={r.date + r.variant + r.period}>
                  <td><strong>{r.variant}</strong><span className="muted block">{r.family}</span></td>
                  <td className="muted">{PERIOD_LABEL(r.period)}</td>
                  <td className={`num mono ${tone(r.ret_anual_pct)}`}>{r.ret_anual_pct != null ? `${r.ret_anual_pct.toFixed(1)} %` : r.avg_r != null ? `${r.avg_r.toFixed(2)} R` : '—'}</td>
                  <td className={`num mono ${tone(r.sharpe)}`}>{r.sharpe != null ? r.sharpe.toFixed(2) : '—'}</td>
                  <td className="num mono">{r.peor_caida_pct != null ? `${r.peor_caida_pct.toFixed(1)} %` : '—'}</td>
                  <td className="num mono">
                    {r.p == null ? '—' : <span className={r.p <= REQUIRED_P ? 'badge ok' : r.p < 0.05 ? 'badge mid' : ''}>{r.p.toFixed(4)}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.length > 15 && (
          <button className="more" onClick={() => setAll((v) => !v)}>
            {all ? 'Mostrar menos' : `Ver las ${rows.length} pruebas`}
          </button>
        )}
      </div>
    </section>
  );
}

const tone = (v?: number) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');

/** Sharpe contra fuerza estadística (−log10 p): arriba a la derecha está lo que vale la pena mirar. */
function Scatter() {
  const pts = ROWS.filter((r) => r.sharpe != null && r.p != null).map((r) => ({ r, x: r.sharpe as number, y: -Math.log10(Math.max(r.p as number, 1e-4)) }));
  const W = 720, H = 300, P = { l: 48, r: 16, t: 16, b: 40 };
  const xs = pts.map((p) => p.x), xMin = Math.min(-0.6, ...xs), xMax = Math.max(2, ...xs), yMax = 4;
  const X = (v: number) => P.l + ((v - xMin) / (xMax - xMin)) * (W - P.l - P.r);
  const Y = (v: number) => H - P.b - (v / yMax) * (H - P.t - P.b);
  const [hover, setHover] = useState<string | null>(null);
  // Marcas cada 0,5 o cada 1 según el rango, para cubrir todo el eje.
  const stepX = xMax - xMin > 4 ? 1 : 0.5;
  const xTicks: number[] = [];
  for (let t = Math.ceil(xMin / stepX) * stepX; t <= xMax + 1e-9; t += stepX) xTicks.push(Number(t.toFixed(1)));

  return (
    <figure className="scatter">
      <figcaption className="h3">Sharpe contra fuerza estadística</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Gráfico de dispersión de Sharpe contra valor p">
        {[0, 1, 2, 3, 4].map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={Y(t)} y2={Y(t)} stroke="var(--border)" />
            <text x={P.l - 8} y={Y(t) + 4} textAnchor="end" className="axis">{t === 0 ? '1' : `1e-${t}`}</text>
          </g>
        ))}
        <line x1={X(0)} x2={X(0)} y1={P.t} y2={H - P.b} stroke="var(--border-strong)" />
        <line x1={P.l} x2={W - P.r} y1={Y(-Math.log10(0.05))} y2={Y(-Math.log10(0.05))} stroke="var(--warn)" strokeDasharray="4 4" />
        <text x={W - P.r} y={Y(-Math.log10(0.05)) - 6} textAnchor="end" className="axis" fill="var(--warn)">p = 0,05</text>
        <line x1={P.l} x2={W - P.r} y1={Y(-Math.log10(REQUIRED_P))} y2={Y(-Math.log10(REQUIRED_P))} stroke="var(--up)" strokeDasharray="4 4" />
        <text x={W - P.r} y={Y(-Math.log10(REQUIRED_P)) - 6} textAnchor="end" className="axis" fill="var(--up)">barra corregida</text>
        {pts.map(({ r, x, y }) => (
          <circle key={r.variant + r.period} cx={X(x)} cy={Y(y)} r={hover === r.variant + r.period ? 7 : 5}
            fill={(r.p as number) <= REQUIRED_P ? 'var(--up)' : x > 0 ? 'var(--accent)' : 'var(--down)'} fillOpacity={0.75}
            onMouseEnter={() => setHover(r.variant + r.period)} onMouseLeave={() => setHover(null)}>
            <title>{`${r.variant} · ${PERIOD_LABEL(r.period)} · Sharpe ${x.toFixed(2)} · p ${(r.p as number).toFixed(4)}`}</title>
          </circle>
        ))}
        {xTicks.map((t) => (
          <text key={t} x={X(t)} y={H - P.b + 18} textAnchor="middle" className="axis">{t}</text>
        ))}
        <text x={(W + P.l) / 2} y={H - 4} textAnchor="middle" className="axis">Sharpe anual</text>
      </svg>
      <p className="note">Cada punto es una prueba. Más arriba, menos probable que sea suerte. Pasa el cursor para ver cuál es.</p>
    </figure>
  );
}
