import Bots from './components/Bots';
import Lab from './components/Lab';
import Pipeline from './components/Pipeline';
import Results from './components/Results';
import Safety from './components/Safety';
import Simulators from './components/Simulators';
import registry from './research/registry.json';

const REPO = 'https://github.com/Ang3lRamos/a1Tradingbot-';

export default function App() {
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <a href="#inicio" className="brand">
            <span className="brand-mark" aria-hidden>
              <svg width="16" height="16" viewBox="0 0 32 32"><path d="M5 23l7-8 5 4 10-12" fill="none" stroke="#34d399" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </span>
            mt5bot
          </a>
          <nav className="nav" aria-label="Secciones">
            <a href="#bots">Bots</a>
            <a href="#flujo">Cómo opera</a>
            <a href="#simulador">Simulador</a>
            <a href="#laboratorio">Laboratorio</a>
            <a href="#resultados">Resultados</a>
          </nav>
          <a className="gh" href={REPO} target="_blank" rel="noreferrer">Código</a>
        </div>
      </header>

      <main className="shell" id="inicio">
        <section className="hero">
          <p className="eyebrow">MetaTrader 5 · Alpaca · Python</p>
          <h1>Un bot de trading que primero cuida el riesgo.</h1>
          <p className="lead">
            En cada vela busca una señal, calcula los lotes por riesgo y pasa la orden por un filtro que puede bloquearla.
            Todo queda en una bitácora, y cada idea nueva se prueba antes en un laboratorio que se corrige por azar.
          </p>
          <div className="grid-4 kpis">
            <Kpi value="4" label="bots en cuentas demo" />
            <Kpi value="0,5 %" label="riesgo máximo por operación" />
            <Kpi value={String(registry.length)} label="pruebas en el laboratorio" />
            <Kpi value="102" label="tests que corren sin MT5" />
          </div>
        </section>

        <Bots />
        <Pipeline />
        <Simulators />
        <Lab />
        <Results />
        <Safety />
      </main>

      <footer className="footer">
        <div className="shell">
          Proyecto personal de Angel Ramos. Opera en cuentas demo y de práctica; nada aquí es una recomendación de inversión.
        </div>
      </footer>
    </>
  );
}

function Kpi({ value, label }: { value: string; label: string }) {
  return (
    <div className="card kpi">
      <span className="kpi-value mono">{value}</span>
      <span className="kpi-label">{label}</span>
    </div>
  );
}
