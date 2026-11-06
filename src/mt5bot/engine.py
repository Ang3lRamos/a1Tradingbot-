"""El ciclo del bot: cada minuto revisa cierres forzados; en cada vela nueva mueve stops y busca entradas."""
import logging
import time as clock
from datetime import datetime, timedelta

from mt5bot.config import Settings
from mt5bot.core.indicators import atr
from mt5bot.core.models import RiskState
from mt5bot.core.order_plan import plan_at_price
from mt5bot.core.position_rules import forced_close_reason, next_stop
from mt5bot.core.risk import evaluate
from mt5bot.core.strategies import get_strategy
from mt5bot.io.journal import Journal
from mt5bot.io.mt5_gateway import Mt5Error, Mt5Gateway

log = logging.getLogger("mt5bot")

# El ciclo no se alinea al reloj local: la hora del servidor tiene otro huso y las velas H4 quedarían desfasadas.
POLL_SECONDS = 60


class Bot:
    def __init__(self, gateway: Mt5Gateway, settings: Settings, journal: Journal):
        self.gateway = gateway
        self.settings = settings
        self.journal = journal
        self.strategy = get_strategy(settings.strategy.name)
        self.last_bar_seen: dict[str, datetime] = {}

    def check_account_allowed(self) -> None:
        bot = self.settings.bot
        if bot.mode == "live" and not self.gateway.is_demo_account() and not bot.allow_real_account:
            raise Mt5Error("modo live en cuenta REAL bloqueado: usa una cuenta demo o pon allow_real_account = true")

    def run_forever(self) -> None:
        self.check_account_allowed()
        log.info("bot iniciado en modo %s, estrategia %s, %s %s", self.settings.bot.mode,
                 self.settings.strategy.name, self.settings.bot.timeframe, self.settings.bot.symbols)
        while not self._kill_switch_pulled():
            for symbol in self.settings.bot.symbols:
                try:
                    self.run_cycle(symbol)
                except Mt5Error as error:
                    log.error("%s: %s", symbol, error)
                    self.journal.log("error", {"message": str(error)}, symbol)
            self._sleep(POLL_SECONDS)
        self._flatten_all("kill switch")

    def run_cycle(self, symbol: str) -> None:
        settings = self.settings
        server_now, bid, ask = self.gateway.quote(symbol)
        reason = forced_close_reason(server_now, settings.strategy.flat_by, settings.risk.friday_close)
        if reason:
            self._close_positions(symbol, server_now, reason)

        bars = self.gateway.closed_bars(symbol, settings.bot.timeframe, self.strategy.bars_needed(settings.strategy))
        last_bar_time = bars["time"].iloc[-1].to_pydatetime()
        if self.last_bar_seen.get(symbol) == last_bar_time:
            return
        self.last_bar_seen[symbol] = last_bar_time

        self._apply_exit_rule(symbol, bars, server_now)
        current_atr = float(atr(bars, settings.strategy.atr_period).iloc[-1])
        self._move_stops(symbol, server_now, bid, ask, current_atr)

        signal = self.strategy.find_signal(symbol, bars, settings.strategy)
        if signal is None or signal.bar_time != last_bar_time:
            return
        # El backtest entra a la apertura de la vela siguiente: se mide el atraso desde esa apertura, que tras un
        # fin de semana es la reapertura del mercado (no el cierre de la vela del viernes).
        next_open = self.gateway.forming_bar_time(symbol, settings.bot.timeframe)
        if server_now - next_open > timedelta(minutes=settings.bot.max_entry_delay_minutes):
            self.journal.log("skipped", {"reason": f"la vela siguiente a la señal abrió a las {next_open:%H:%M}"},
                             symbol, server_now)
            return
        self._try_entry(signal, server_now, bid, ask)

    def _try_entry(self, signal, server_now: datetime, bid: float, ask: float) -> None:
        settings, symbol = self.settings, signal.symbol
        self.journal.log("signal", vars(signal), symbol, server_now)
        if self.gateway.positions(settings.bot.magic, symbol):
            self.journal.log("skipped", {"reason": "ya hay una posición abierta en el símbolo"}, symbol, server_now)
            return

        spec = self.gateway.symbol_spec(symbol)
        balance, equity = self.gateway.balance_and_equity()
        fill_price = ask if signal.side == "buy" else bid
        plan = plan_at_price(signal, fill_price, equity, settings.risk.risk_per_trade_pct,
                             spec, settings.strategy.target_r)
        if plan is None:
            self.journal.log("skipped", {"reason": "el precio ya pasó el stop"}, symbol, server_now)
            return

        realized_today, trades_today = self.gateway.today_deals(settings.bot.magic, server_now)
        state = RiskState(
            now=server_now,
            balance_start_of_day=balance - realized_today,
            equity=equity,
            pnl_today=equity - (balance - realized_today),
            trades_today=trades_today,
            open_positions=len(self.gateway.positions(settings.bot.magic)),
            spread_points=round((ask - bid) / spec.point),
        )
        decision = evaluate(plan, state, settings.risk)
        detail = {"lots": plan.lots, "risk_money": round(plan.risk_money, 2), "entry": plan.signal.entry,
                  "stop": plan.signal.stop, "target": plan.signal.target, "reasons": decision.reasons}
        if not decision.passed:
            log.info("%s bloqueada: %s", symbol, "; ".join(decision.reasons))
            self.journal.log("blocked", detail, symbol, server_now)
            return
        if settings.bot.mode == "dry_run":
            log.info("%s [dry_run] %s %.2f lotes, riesgo %.2f", symbol, signal.side, plan.lots, plan.risk_money)
            self.journal.log("dry_run", detail, symbol, server_now)
            return

        result = self.gateway.send_market_order(plan, settings.bot.magic, f"{settings.strategy.name} {signal.side}")
        self.journal.record_position(result.order, plan, server_now)
        self.journal.log("order_sent", {**detail, "ticket": result.order, "price": result.price}, symbol, server_now)
        log.info("%s orden %s enviada: %.2f lotes a %s", symbol, signal.side, plan.lots, result.price)

    def _apply_exit_rule(self, symbol: str, bars, server_now: datetime) -> None:
        if self.strategy.exit_due is None:
            return
        for position in self.gateway.positions(self.settings.bot.magic, symbol):
            opened_at = self.journal.opened_at(position.ticket)
            if opened_at is not None and self.strategy.exit_due(bars, opened_at, self.settings.strategy):
                self.gateway.close_position(position, "regla de salida")
                self.journal.log("closed", {"ticket": position.ticket, "reason": "regla de salida"}, symbol, server_now)

    def _move_stops(self, symbol: str, server_now: datetime, bid: float, ask: float, current_atr: float) -> None:
        strategy = self.settings.strategy
        for position in self.gateway.positions(self.settings.bot.magic, symbol):
            initial_stop = self.journal.initial_stop(position.ticket)
            if initial_stop is None:
                continue
            direction = 1 if self.gateway.position_is_buy(position) else -1
            price = bid if direction == 1 else ask
            new_stop = next_stop(direction, position.price_open, initial_stop, position.sl, price,
                                 current_atr, strategy.breakeven_at_r, strategy.trail_atr)
            if new_stop is not None:
                self.gateway.modify_stop(position, new_stop)
                self.journal.log("stop_moved", {"ticket": position.ticket, "from": position.sl, "to": new_stop},
                                 symbol, server_now)

    def _close_positions(self, symbol: str, server_now: datetime, reason: str) -> None:
        for position in self.gateway.positions(self.settings.bot.magic, symbol):
            self.gateway.close_position(position, reason)
            self.journal.log("closed", {"ticket": position.ticket, "reason": reason}, symbol, server_now)

    def _flatten_all(self, reason: str) -> None:
        for position in self.gateway.positions(self.settings.bot.magic):
            self.gateway.close_position(position, reason)
            self.journal.log("closed", {"ticket": position.ticket, "reason": reason}, position.symbol)
        log.warning("bot detenido: %s", reason)

    def _kill_switch_pulled(self) -> bool:
        return self.settings.bot.kill_switch_file.exists()

    def _sleep(self, seconds: int) -> None:
        # Pasos de 1 s para que el kill switch actúe en segundos.
        deadline = clock.time() + seconds
        while clock.time() < deadline and not self._kill_switch_pulled():
            clock.sleep(1)
