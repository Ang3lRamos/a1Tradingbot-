"""Qué avisar por Telegram, a partir de lo que arma el panel. Lógica pura: recibe el estado anterior y devuelve el nuevo.

Avisa operaciones abiertas y cerradas, errores que anotan los bots, bots sin latido y brokers que no responden
(y cuando vuelven). El estado guarda lo ya avisado para no repetirlo.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from mt5bot.report import AccountView, BotView

SIDES = {"buy": "Compra", "sell": "Venta"}
SILENCE = timedelta(minutes=10)  # el bot escribe su latido cada minuto; 10 sin latido = caído


@dataclass
class AlertState:
    sent: set[str] = field(default_factory=set)          # operaciones y errores ya avisados
    down: set[str] = field(default_factory=set)          # bots (magic) avisados como caídos
    brokers_down: set[str] = field(default_factory=set)  # cuentas avisadas como sin respuesta


def _money(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def trade_alerts(bot: BotView, sent: set[str]) -> list[tuple[str, str]]:
    """(clave, mensaje) de cada apertura o cierre que no está en `sent`. La clave identifica la operación."""
    alerts = []
    for p in bot.open_positions:
        key = f"{bot.magic}-open-{p['ticket']}"
        if key not in sent:
            alerts.append((key, f"Nueva operación · {bot.name}\n{SIDES[p['side']]} {p['symbol']}: "
                                f"{p['volume']:g} a {_money(p['price_open'])}, stop {_money(p['sl'])}"))
    for t in bot.trades:
        key = f"{bot.magic}-close-{t['position']}"
        if key not in sent:
            r = "" if t["r"] is None else f" ({t['r']:+.2f} R)"
            alerts.append((key, f"Operación cerrada · {bot.name}\n{SIDES[t['side']]} {t['symbol']}: "
                                f"{t['pnl']:+,.2f} USD{r}, entrada {_money(t['entry'])} → salida {_money(t['exit'])}"))
    return alerts


def error_alert(bot: BotView, sent: set[str]) -> tuple[list[str], str | None]:
    """Errores nuevos de la bitácora del bot, juntos en un solo mensaje (pueden ser varios por vuelta)."""
    new = [e for e in bot.events if e["kind"] == "error" and f"{bot.magic}-error-{e['logged_at']}" not in sent]
    if not new:
        return [], None
    last = new[0]  # los eventos vienen del más reciente al más viejo
    text = (f"Error · {bot.name}\n{len(new)} error(es) nuevo(s). Último ({last['logged_at'][11:16]}, "
            f"{last['symbol'] or 'general'}): {last['detail'].get('message', last['detail'])}")
    return [f"{bot.magic}-error-{e['logged_at']}" for e in new], text


def liveness_alert(bot: BotView, down: set[str], now: datetime) -> tuple[bool, str | None]:
    """(¿está caído?, mensaje si cambió respecto a lo ya avisado)."""
    is_down = bot.last_beat is None or now - bot.last_beat > SILENCE
    was_down = str(bot.magic) in down
    if is_down and not was_down:
        since = f"desde {bot.last_beat:%d/%m %H:%M}" if bot.last_beat else "sin latido registrado"
        return True, f"Bot caído · {bot.name}\nSin latido {since}. Revisar que el PC, el bot y el broker estén abiertos."
    if was_down and not is_down:
        return False, f"Bot de vuelta · {bot.name}\nEl latido volvió."
    return is_down, None


def broker_alert(account: AccountView, brokers_down: set[str]) -> str | None:
    was_down = account.label in brokers_down
    if account.error and not was_down:
        return f"Broker sin respuesta · {account.label}\n{account.error}"
    if was_down and not account.error:
        return f"Broker de vuelta · {account.label}"
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
