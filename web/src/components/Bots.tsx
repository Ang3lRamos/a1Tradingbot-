// Los cuatro bots que corren en demo (ver CLAUDE.md, "Bots en la demo").
const BOTS = [
  {
    name: 'Donchian H4',
    broker: 'MetaTrader 5',
    markets: '11 pares de divisas y oro',
    rule: 'Ruptura del máximo o mínimo de 20 velas, solo a favor de la EMA 200. Stop a 2 ATR y trailing a 3 ATR.',
    status: 'En prueba',
    tone: 'warn',
  },
  {
    name: 'RSI2 índices',
    broker: 'MetaTrader 5',
    markets: 'US500, US100, US30',
    rule: 'Compra cuando el RSI de 2 días cae bajo 10 con el precio sobre la media de 200; sale sobre la media de 5.',
    status: 'En prueba',
    tone: 'warn',
  },
  {
    name: 'RSI2 ETFs',
    broker: 'Alpaca',
    markets: 'SPY, QQQ, DIA',
    rule: 'La misma regla RSI2 con acciones fraccionadas, para probar la vía de una cuenta pequeña.',
    status: 'Con ventaja en backtest',
    tone: 'up',
  },
  {
    name: 'RSI2 cripto',
    broker: 'Alpaca',
    markets: 'BTC, ETH, SOL',
    rule: 'RSI2 diario 24/7 al contado, con el stop como orden aparte en el servidor.',
    status: 'Prueba técnica',
    tone: 'muted',
  },
];

const TONE: Record<string, string> = { up: 'var(--up)', warn: 'var(--warn)', muted: 'var(--text-3)' };

export default function Bots() {
  return (
    <section id="bots">
      <div className="section-head">
        <p className="eyebrow">01 · Bots</p>
        <h2>Cuatro bots, el mismo motor</h2>
        <p>Cada bot es un archivo de configuración: estrategia, mercados y límites. El código que decide y el que ejecuta es el mismo.</p>
      </div>
      <div className="grid-2">
        {BOTS.map((b) => (
          <article key={b.name} className="card bot">
            <div className="bot-head">
              <h3 className="h3">{b.name}</h3>
              <span className="pill" style={{ color: TONE[b.tone] }}>
                <span className="dot" /> {b.status}
              </span>
            </div>
            <p className="bot-meta mono">{b.broker} · {b.markets}</p>
            <p className="bot-rule">{b.rule}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
