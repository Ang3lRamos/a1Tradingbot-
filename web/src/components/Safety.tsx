const RULES = [
  ['Demo por defecto', 'Arranca en dry_run. En una cuenta real se niega a operar salvo que se habilite a mano.'],
  ['Stop en el servidor', 'Stop y objetivo viajan dentro de la orden: protegen la posición aunque el PC se apague.'],
  ['Kill switch', 'Un archivo STOP en la carpeta cierra las posiciones del bot y lo detiene en menos de un segundo.'],
  ['Solo lo suyo', 'Identifica sus operaciones por un número mágico: nunca toca operaciones manuales.'],
  ['Pérdida diaria real', 'El límite del día incluye lo flotante, no solo lo cerrado.'],
  ['Avisos', 'Telegram avisa operaciones, errores, bots sin latido y brokers que no responden.'],
];

export default function Safety() {
  return (
    <section id="seguridad">
      <div className="section-head">
        <p className="eyebrow">06 · Seguridad</p>
        <h2>Reglas que no se rompen</h2>
      </div>
      <div className="grid-3">
        {RULES.map(([title, text]) => (
          <div key={title} className="card rule">
            <h3 className="h3">{title}</h3>
            <p>{text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
