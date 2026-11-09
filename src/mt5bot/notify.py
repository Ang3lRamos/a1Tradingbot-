"""Qué avisar por Telegram: operaciones abiertas y cerradas que aún no se avisaron. Lógica pura sobre lo del panel."""
from mt5bot.report import BotView

SIDES = {"buy": "Compra", "sell": "Venta"}


def _money(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def pending_alerts(bots: list[BotView], sent: set[str]) -> list[tuple[str, str]]:
    """(clave, mensaje) de cada apertura o cierre que no está en `sent`. La clave identifica la operación."""
    alerts = []
    for bot in bots:
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
