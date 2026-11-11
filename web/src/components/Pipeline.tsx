const STEPS = [
  { title: 'Vela cerrada', text: 'Cada minuto revisa si cerró una vela nueva. Si la señal llega más de 5 minutos tarde, no entra.' },
  { title: 'Señal', text: 'La estrategia mira solo velas cerradas: nunca el futuro. Hay tests que lo comprueban.' },
  { title: 'Precio real', text: 'Ajusta la señal al ask o al bid del momento, con el spread de verdad.' },
  { title: 'Lotes por riesgo', text: 'Calcula cuántos lotes caben en el 0,5 % del capital y redondea siempre hacia abajo.' },
  { title: 'Filtro de riesgo', text: 'PASS o BLOCK con todas las razones: pérdida del día, spread, horario, posiciones…' },
  { title: 'Orden y bitácora', text: 'La orden sale con stop y objetivo dentro; todo queda registrado en SQLite.' },
];

export default function Pipeline() {
  return (
    <section id="flujo">
      <div className="section-head">
        <p className="eyebrow">02 · Cómo opera</p>
        <h2>Seis pasos en cada vela</h2>
        <p>Las reglas viven en una capa de lógica pura, sin MetaTrader ni red. El backtest usa exactamente las mismas funciones que el bot.</p>
      </div>
      <ol className="pipeline">
        {STEPS.map((s, i) => (
          <li key={s.title} className="card step">
            <span className="step-n mono">{String(i + 1).padStart(2, '0')}</span>
            <h3 className="h3">{s.title}</h3>
            <p>{s.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
