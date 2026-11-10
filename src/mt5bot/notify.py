"""Qué avisar por Telegram, a partir de lo que arma el panel. Lógica pura: recibe el estado anterior y devuelve el nuevo.

Avisa operaciones abiertas y cerradas, errores que anotan los bots, bots sin latido y brokers que no responden
(y cuando vuelven). El estado guarda lo ya avisado para no repetirlo. Los mensajes van en HTML de Telegram: todo
texto que viene de afuera (símbolos, nombres, errores) pasa por `escape`.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape

from mt5bot.report import AccountView, BotView

SIDES = {"buy": ("🟢", "Compra"), "sell": ("🔴", "Venta")}
SILENCE = timedelta(minutes=10)  # el bot escribe su latido cada minuto; 10 sin latido = caído
ERRORS_SHOWN = 3
ERROR_CHARS = 200


@dataclass
class AlertState:
    sent: set[str] = field(default_factory=set)          # operaciones y errores ya avisados
    down: set[str] = field(default_factory=set)          # bots (magic) avisados como caídos
    brokers_down: set[str] = field(default_factory=set)  # cuentas avisadas como sin respuesta


def _price(value: float | None) -> str:
    """Forex con 5 decimales; índices, ETF y cripto con 2."""
    if value is None:
        return "—"
    return f"{value:,.2f}" if abs(value) >= 10 else f"{value:.5f}"


def _move(start: float, end: float | None) -> str:
    return "" if not start or end is None else f" ({(end - start) / start * 100:+.2f} %)"


def _duration(opened: datetime, closed: datetime) -> str:
    minutes = int((closed - opened).total_seconds() // 60)
    days, hours = divmod(minutes // 60, 24)
    if days:
        return f"{days} d {hours} h"
    return f"{hours} h {minutes % 60} min" if hours else f"{minutes} min"


def _header(icon: str, title: str, bot_name: str) -> str:
    return f"{icon} <b>{title}</b>\n<i>{escape(bot_name)}</i>\n\n"


def open_message(bot: BotView, p: dict) -> str:
    icon, side = SIDES[p["side"]]
    return (_header(icon, f"{side} {escape(p['symbol'])}", bot.name)
            + f"Entrada: <b>{_price(p['price_open'])}</b>\n"
              f"Stop: {_price(p['sl'])}{_move(p['price_open'], p['sl'])}\n"
              f"Tamaño: {p['volume']:g}")


def close_message(bot: BotView, t: dict) -> str:
    won = t["pnl"] >= 0
    r = "" if t["r"] is None else f" · {t['r']:+.2f} R"
    title = f"{'Ganancia' if won else 'Pérdida'} {t['pnl']:+,.2f} USD{r}"
    return (_header("✅" if won else "❌", title, bot.name)
            + f"{SIDES[t['side']][1]} {escape(t['symbol'])} cerrada\n"
              f"Entrada {_price(t['entry'])} → salida {_price(t['exit'])}{_move(t['entry'], t['exit'])}\n"
              f"Duración: {_duration(t['opened'], t['closed'])}")


def trade_alerts(bot: BotView, sent: set[str]) -> list[tuple[str, str]]:
    """(clave, mensaje) de cada apertura o cierre que no está en `sent`. La clave identifica la operación."""
    alerts = [(f"{bot.magic}-open-{p['ticket']}", p) for p in bot.open_positions]
    closes = [(f"{bot.magic}-close-{t['position']}", t) for t in bot.trades]
    return ([(k, open_message(bot, p)) for k, p in alerts if k not in sent]
            + [(k, close_message(bot, t)) for k, t in closes if k not in sent])


def _error_line(event: dict) -> str:
    message = str(event["detail"].get("message", event["detail"]))
    if len(message) > ERROR_CHARS:
        message = message[:ERROR_CHARS] + "…"
    return f"• {event['logged_at'][11:16]} {escape(event['symbol'] or 'general')}: <code>{escape(message)}</code>"


def error_alert(bot: BotView, sent: set[str]) -> tuple[list[str], str | None]:
    """Errores nuevos de la bitácora del bot, juntos en un solo mensaje (pueden ser varios por vuelta)."""
    new = [e for e in bot.events if e["kind"] == "error" and f"{bot.magic}-error-{e['logged_at']}" not in sent]
    if not new:
        return [], None
    lines = [_error_line(e) for e in new[:ERRORS_SHOWN]]  # los eventos vienen del más reciente al más viejo
    if len(new) > ERRORS_SHOWN:
        lines.append(f"… y {len(new) - ERRORS_SHOWN} más (ver panel)")
    title = f"{len(new)} error{'es' if len(new) > 1 else ''}"
    return [f"{bot.magic}-error-{e['logged_at']}" for e in new], _header("⚠️", title, bot.name) + "\n".join(lines)


def liveness_alert(bot: BotView, down: set[str], now: datetime) -> tuple[bool, str | None]:
    """(¿está caído?, mensaje si cambió respecto a lo ya avisado)."""
    is_down = bot.last_beat is None or now - bot.last_beat > SILENCE
    was_down = str(bot.magic) in down
    if is_down and not was_down:
        since = f"desde el {bot.last_beat:%d/%m %H:%M}" if bot.last_beat else "registrado"
        return True, (_header("🛑", "Bot caído", bot.name)
                      + f"Sin latido {since}.\nRevisa que el PC, el bot y el broker estén abiertos.")
    if was_down and not is_down:
        return False, _header("💚", "Bot de vuelta", bot.name) + "El latido volvió."
    return is_down, None


def broker_alert(account: AccountView, brokers_down: set[str]) -> str | None:
    was_down = account.label in brokers_down
    if account.error and not was_down:
        return f"📡 <b>Broker sin respuesta</b> · {escape(account.label)}\n\n<code>{escape(account.error)}</code>"
    if was_down and not account.error:
        return f"💚 <b>Broker de vuelta</b> · {escape(account.label)}"
    return None


def pending_alerts(bots: list[BotView], accounts: list[AccountView], state: AlertState, now: datetime,
                   check_liveness: bool = True) -> tuple[list[str], AlertState]:
    """Mensajes por enviar y el estado nuevo. Sin check_liveness (el vigilante recién arranca) no juzga latidos."""
    messages, new = [], AlertState(set(state.sent), set(state.down), set(state.brokers_down))
    for bot in bots:
        for key, text in trade_alerts(bot, state.sent):
            messages.append(text)
            new.sent.add(key)
        keys, text = error_alert(bot, state.sent)
        new.sent.update(keys)
        messages += [text] if text else []
        if check_liveness:
            is_down, text = liveness_alert(bot, state.down, now)
            (new.down.add if is_down else new.down.discard)(str(bot.magic))
            messages += [text] if text else []
    for account in accounts:
        text = broker_alert(account, state.brokers_down)
        (new.brokers_down.add if account.error else new.brokers_down.discard)(account.label)
        messages += [text] if text else []
    return messages, new
