"""Panel de los bots: arma operaciones cerradas desde el historial de MT5 y genera una página HTML local.

Lógica pura: recibe datos ya leídos (deals, posiciones, bitácora) y devuelve texto. La lectura vive en main.py.
"""
from dataclasses import dataclass
from datetime import datetime
from html import escape

from mt5bot.config import BacktestConfig

MIN_TRADES_TO_COMPARE = 30
REFRESH_SECONDS = 60  # el navegador recarga el archivo; el vigilante lo regenera cada pocos minutos
EVENT_LABELS = {"signal": "Señal", "dry_run": "Simulada", "order_sent": "Orden enviada", "blocked": "Bloqueada",
                "skipped": "Descartada", "closed": "Cerrada", "stop_moved": "Stop movido", "error": "Error"}


@dataclass(frozen=True)
class BotView:
    name: str
    description: str
    expected: BacktestConfig
    trades: list[dict]
    open_positions: list[dict]
    events: list[dict]
    status: str
    magic: int = 0
    last_beat: datetime | None = None


@dataclass(frozen=True)
class AccountView:
    label: str
    balance: float | None
    equity: float | None
    error: str | None = None  # el broker no respondió: sus bots no salen en esta vuelta


def closed_trades(deals: list[dict], positions_info: dict[int, dict]) -> list[dict]:
    """Una fila por posición ya cerrada del todo: precios promedio, resultado en USD y en R."""
    by_position: dict[int, list[dict]] = {}
    for deal in deals:
        by_position.setdefault(deal["position"], []).append(deal)
    trades = []
    for position, group in by_position.items():
        ins = [d for d in group if d["entry"]]
        outs = [d for d in group if not d["entry"]]
        opened_volume, closed_volume = sum(d["volume"] for d in ins), sum(d["volume"] for d in outs)
        if not ins or closed_volume + 1e-9 < opened_volume:
            continue
        pnl = sum(d["money"] for d in group)
        risk = positions_info.get(position, {}).get("risk_money")
        trades.append({
            "position": position, "symbol": ins[0]["symbol"], "side": ins[0]["side"],
            "opened": min(d["time"] for d in ins), "closed": max(d["time"] for d in outs),
            "entry": sum(d["price"] * d["volume"] for d in ins) / opened_volume,
            "exit": sum(d["price"] * d["volume"] for d in outs) / closed_volume,
            "pnl": pnl, "r": pnl / risk if risk else None,
        })
    return sorted(trades, key=lambda t: t["closed"])


def summary(trades: list[dict]) -> dict:
    r_values = [t["r"] for t in trades if t["r"] is not None]
    return {
        "n": len(trades),
        "win_rate": 100 * sum(t["pnl"] > 0 for t in trades) / len(trades) if trades else None,
        "avg_r": sum(r_values) / len(r_values) if r_values else None,
        "total": sum(t["pnl"] for t in trades),
    }


def liveness(last_beat: datetime | None, now: datetime, max_silence_minutes: int = 5) -> str:
    """Estado del bot según su latido (lo escribe cada minuto mientras corre)."""
    if last_beat is None:
        return "⚪ Sin latido registrado (el bot aún no arranca con la versión que lo escribe, o nunca corrió)."
    minutes = (now - last_beat).total_seconds() / 60
    if minutes <= max_silence_minutes:
        return f"🟢 Activo: último latido hace {max(minutes, 0):.0f} min."
    return f"🔴 SIN LATIDO desde {last_beat:%d/%m %H:%M} ({minutes / 60:.1f} h): revisar que el bot y MT5 estén abiertos."


def verdict(stats: dict, expected: BacktestConfig) -> str:
    if stats["n"] == 0:
        return "Todavía no hay operaciones cerradas."
    if stats["n"] < MIN_TRADES_TO_COMPARE:
        return (f"{stats['n']} operaciones cerradas: muy pocas para comparar con el backtest "
                f"(hacen falta unas {MIN_TRADES_TO_COMPARE}). Cualquier resultado aún puede ser suerte.")
    gap = stats["avg_r"] - expected.expected_avg_r
    if abs(gap) < 0.15:
        return "Se comporta como dice el backtest."
    return "Va mejor que el backtest." if gap > 0 else "Va peor que el backtest: revisar en la reunión."


def cumulative_r_svg(trades: list[dict]) -> str:
    r_values = [t["r"] for t in trades if t["r"] is not None]
    if len(r_values) < 2:
        return '<p class="muted">El gráfico aparece con 2 operaciones cerradas o más.</p>'
    points, total = [0.0], 0.0
    for r in r_values:
        total += r
        points.append(total)
    width, height, pad = 640, 180, 28
    low, high = min(points + [0.0]), max(points + [0.0])
    span = (high - low) or 1.0
    x = lambda i: pad + i * (width - 2 * pad) / (len(points) - 1)  # noqa: E731
    y = lambda v: pad + (high - v) * (height - 2 * pad) / span      # noqa: E731
    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(points))
    last = points[-1]
    return (f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="R acumulado">'
            f'<line class="zero" x1="{pad}" x2="{width - pad}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>'
            f'<text x="4" y="{y(0) + 4:.1f}">0R</text>'
            f'<polyline class="curve {"up" if last >= 0 else "down"}" points="{line}"/>'
            f'<circle class="{"up" if last >= 0 else "down"}" cx="{x(len(points) - 1):.1f}" cy="{y(last):.1f}" r="4"/>'
            f'<text x="{width - pad}" y="{max(14, y(last) - 8):.1f}" text-anchor="end">{last:+.2f}R</text></svg>')


def _money(value: float) -> str:
    return f'<span class="{"pos" if value >= 0 else "neg"}">{value:+,.2f}</span>'


def _event_text(event: dict) -> str:
    d, kind = event["detail"], event["kind"]
    if kind in ("blocked", "skipped", "closed"):
        return "; ".join(d.get("reasons") or [d.get("reason", "")])
    if kind == "order_sent":
        return f"{d['lots']} lotes, riesgo {d['risk_money']} USD, stop {d['stop']:.5g}"
    if kind == "signal":
        return f"{d['side']}: {d.get('reason', '')}"
    if kind == "stop_moved":
        return f"de {d['from']:.5g} a {d['to']:.5g}"
    return d.get("message", "")


def _bot_section(bot: BotView) -> str:
    stats, exp = summary(bot.trades), bot.expected
    fmt = lambda v, spec: "—" if v is None else format(v, spec)  # noqa: E731
    open_rows = "".join(
        f"<tr><td>{escape(p['symbol'])}</td><td>{'compra' if p['side'] == 'buy' else 'venta'}</td>"
        f"<td class='num'>{p['volume']}</td><td class='num'>{p['price_open']:.5g}</td><td class='num'>{p['price_now']:.5g}</td>"
        f"<td class='num'>{p['sl']:.5g}</td><td class='num'>{_money(p['profit'])}</td>"
        f"<td class='num'>{fmt(p['r'], '+.2f')}R</td></tr>" for p in bot.open_positions
    ) or "<tr><td colspan='8' class='muted'>Sin posiciones abiertas.</td></tr>"
    trade_rows = "".join(
        f"<tr><td>{t['closed']:%d %b %H:%M}</td><td>{escape(t['symbol'])}</td>"
        f"<td>{'compra' if t['side'] == 'buy' else 'venta'}</td><td class='num'>{_money(t['pnl'])}</td>"
        f"<td class='num'>{fmt(t['r'], '+.2f')}R</td></tr>" for t in reversed(bot.trades[-15:])
    ) or "<tr><td colspan='5' class='muted'>Sin operaciones cerradas.</td></tr>"
    event_rows = "".join(
        f"<tr><td>{escape(str(e['server_time'] or e['logged_at'])[5:16].replace('T', ' '))}</td>"
        f"<td>{escape(e['symbol'] or '')}</td><td><span class='tag {e['kind']}'>{EVENT_LABELS.get(e['kind'], e['kind'])}</span></td>"
        f"<td>{escape(_event_text(e))}</td></tr>" for e in bot.events
    ) or "<tr><td colspan='4' class='muted'>Sin eventos.</td></tr>"
    return f"""
<section class="bot">
  <header><h2>{escape(bot.name)}</h2><p class="muted">{escape(bot.description)}</p>
  <p class="status">{escape(bot.status)}</p></header>
  <div class="stats">
    <div><span class="k">Operaciones cerradas</span><span class="v">{stats['n']}</span>
      <span class="d">backtest: ~{exp.expected_trades_per_month:g} al mes</span></div>
    <div><span class="k">Aciertos</span><span class="v">{fmt(stats['win_rate'], '.0f')}%</span>
      <span class="d">backtest: {exp.expected_win_rate_pct:g}%</span></div>
    <div><span class="k">R promedio</span><span class="v">{fmt(stats['avg_r'], '+.2f')}</span>
      <span class="d">backtest: {exp.expected_avg_r:+.2f}</span></div>
    <div><span class="k">Resultado cerrado</span><span class="v">{_money(stats['total'])}</span><span class="d">USD</span></div>
  </div>
  <p class="verdict">{escape(verdict(stats, exp))}</p>
  <h3>R acumulado</h3>{cumulative_r_svg(bot.trades)}
  <h3>Posiciones abiertas</h3>
  <div class="scroll"><table><thead><tr><th>Símbolo</th><th>Lado</th><th>Lotes</th><th>Entrada</th><th>Ahora</th>
  <th>Stop</th><th>Flotante USD</th><th>R</th></tr></thead><tbody>{open_rows}</tbody></table></div>
  <h3>Últimas operaciones cerradas</h3>
  <div class="scroll"><table><thead><tr><th>Cierre</th><th>Símbolo</th><th>Lado</th><th>USD</th><th>R</th></tr></thead>
  <tbody>{trade_rows}</tbody></table></div>
  <h3>Últimos eventos</h3>
  <div class="scroll"><table><thead><tr><th>Hora servidor</th><th>Símbolo</th><th>Tipo</th><th>Detalle</th></tr></thead>
  <tbody>{event_rows}</tbody></table></div>
</section>"""


def _account_block(account: AccountView) -> str:
    if account.error:
        return (f'<div class="account"><h2>{escape(account.label)}</h2>'
                f'<p class="neg">Sin conexión: {escape(account.error)}</p></div>')
    return (f'<div class="account"><h2>{escape(account.label)}</h2><div class="stats">'
            f'<div><span class="k">Balance</span><span class="v">{account.balance:,.2f}</span></div>'
            f'<div><span class="k">Equidad</span><span class="v">{account.equity:,.2f}</span></div>'
            f'<div><span class="k">Flotante</span><span class="v">{_money(account.equity - account.balance)}</span></div>'
            f'</div></div>')


def render(bots: list[BotView], accounts: list[AccountView], generated_at: datetime) -> str:
    sections = "".join(_bot_section(bot) for bot in bots)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Panel mt5bot</title>
<meta http-equiv="refresh" content="{REFRESH_SECONDS}">
<style>{STYLE}</style></head><body><main>
<header class="top"><h1>Panel mt5bot</h1>
<p class="muted">Cuentas de prueba · datos de las {generated_at:%H:%M} del {generated_at:%d/%m/%Y} (hora de tu PC) ·
la página se recarga sola cada minuto; los datos se renuevan cada 5 minutos mientras los bots corren</p>
{"".join(_account_block(a) for a in accounts)}</header>
{sections}
<footer class="muted">R = resultado medido en riesgos: 1R es lo que se pierde si toca el stop inicial (~0.5 % de la cuenta).
Se compara con el backtest de cada bot recién desde unas {MIN_TRADES_TO_COMPARE} operaciones.</footer>
</main></body></html>"""


STYLE = """
:root { --bg:#f3f5f7; --surface:#fff; --ink:#16202a; --muted:#5a6773; --rule:#d5dce2; --accent:#2456a4;
  --gain:#17845a; --loss:#c0392f; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root { --bg:#0f151b; --surface:#161f28; --ink:#e4e9ee; --muted:#93a1ad;
  --rule:#2a3540; --accent:#7ca8ee; --gain:#43c08a; --loss:#f06b60; color-scheme: dark; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 "Segoe UI", system-ui, sans-serif; }
main { max-width:1000px; margin:0 auto; padding:24px 16px 48px; display:grid; gap:28px; }
h1 { margin:0; font-size:1.9rem; } h2 { margin:0; font-size:1.4rem; } h3 { margin:18px 0 8px; font-size:1rem; }
p { margin:4px 0; } .muted { color:var(--muted); }
.bot { background:var(--surface); border:1px solid var(--rule); padding:20px; }
.stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:12px; margin-top:14px; }
.stats div { display:grid; gap:2px; } .k { font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }
.v { font-size:1.5rem; font-weight:600; font-variant-numeric:tabular-nums; } .d { font-size:.85rem; color:var(--muted); }
.status { font-weight:600; }
.account { margin-top:16px; } .account h2 { font-size:1.05rem; }
.verdict { margin-top:14px; padding:10px 12px; border-left:3px solid var(--accent); background:var(--bg); }
.pos { color:var(--gain); } .neg { color:var(--loss); }
.scroll { overflow-x:auto; } table { border-collapse:collapse; width:100%; font-size:.9rem; }
th, td { padding:6px 10px; border-bottom:1px solid var(--rule); text-align:left; white-space:nowrap; }
th { font-size:.75rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.tag { font-size:.78rem; padding:1px 6px; border:1px solid var(--rule); }
.tag.order_sent, .tag.closed { border-color:var(--accent); } .tag.blocked, .tag.error { border-color:var(--loss); }
svg { width:100%; height:auto; max-width:640px; } svg text { font-size:11px; fill:var(--muted); }
.zero { stroke:var(--rule); stroke-dasharray:4 3; } .curve { fill:none; stroke-width:2; }
.curve.up { stroke:var(--gain); } .curve.down { stroke:var(--loss); } circle.up { fill:var(--gain); } circle.down { fill:var(--loss); }
footer { font-size:.85rem; }
"""
