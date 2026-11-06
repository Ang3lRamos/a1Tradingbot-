import argparse
import json
import logging
import os
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from mt5bot.config import load_settings

DEFAULT_CONFIG = Path("config/settings.toml")


def connected_gateway():
    from dotenv import load_dotenv
    from mt5bot.io.mt5_gateway import Mt5Gateway

    load_dotenv()
    gateway = Mt5Gateway()
    gateway.connect(int(os.environ["MT5_LOGIN"]), os.environ["MT5_PASSWORD"],
                    os.environ["MT5_SERVER"], os.environ.get("MT5_PATH") or None)
    return gateway


def cmd_run(args) -> None:
    from mt5bot.engine import Bot
    from mt5bot.io.journal import Journal

    settings = load_settings(args.config)
    if args.mode:
        settings = replace(settings, bot=replace(settings.bot, mode=args.mode))
    gateway = connected_gateway()
    journal = Journal(settings.bot.journal_path)
    try:
        Bot(gateway, settings, journal).run_forever()
    finally:
        journal.close()
        gateway.shutdown()


def cmd_download(args) -> None:
    from mt5bot.io.history_files import save_history

    gateway = connected_gateway()
    try:
        # symbol_spec primero: hace symbol_select y da un error claro si el símbolo no existe.
        spec = gateway.symbol_spec(args.symbol)
        end = datetime.now()
        bars = gateway.bars_range(args.symbol, args.timeframe, end - timedelta(days=args.days), end)
        path = save_history(bars, spec, Path("data"), args.timeframe)
    finally:
        gateway.shutdown()
    print(f"{len(bars)} velas guardadas en {path}")


def cmd_backtest(args) -> None:
    from mt5bot.backtest.metrics import monte_carlo, summarize
    from mt5bot.backtest.simulator import run_backtest
    from mt5bot.io.history_files import load_bars, load_spec

    settings = load_settings(args.config)
    spec = load_spec(args.spec)
    result = run_backtest(spec.name, load_bars(args.csv), spec, settings)
    report = {"resumen": summarize(result.trades, settings.backtest.initial_balance),
              "bloqueadas": len(result.blocked)}
    if result.trades:
        bt = settings.backtest
        report["monte_carlo"] = monte_carlo([t.r for t in result.trades],
                                            settings.risk.risk_per_trade_pct, bt.monte_carlo_runs, bt.seed)
    print(json.dumps(report, indent=2, ensure_ascii=False))


BOT_TITLES = {"donchian": "Bot Donchian · seguir tendencias", "rsi2": "Bot RSI2 · comprar caídas en índices",
              "orb": "Bot ORB · ruptura del rango de apertura"}
PANEL_PATH = Path.home() / ".mt5bot" / "panel.html"


def bot_view(gateway, settings):
    """Lee lo que necesita el panel de un bot: bitácora, latido, historial de MT5 y posiciones abiertas."""
    from mt5bot.engine import heartbeat_path
    from mt5bot.io.journal import Journal
    from mt5bot.report import BotView, closed_trades, liveness

    journal = Journal(settings.bot.journal_path)
    try:
        info, events = journal.positions_info(), journal.recent_events(12)
    finally:
        journal.close()
    beat_file = heartbeat_path(settings)
    last_beat = datetime.fromisoformat(beat_file.read_text(encoding="utf-8")) if beat_file.exists() else None
    magic = settings.bot.magic
    open_positions = []
    for p in gateway.positions(magic):
        buy = gateway.position_is_buy(p)
        _, bid, ask = gateway.quote(p.symbol)
        now_price, initial = (bid if buy else ask), info.get(p.ticket, {}).get("initial_stop")
        r = (now_price - p.price_open) * (1 if buy else -1) / abs(p.price_open - initial) if initial else None
        open_positions.append({"symbol": p.symbol, "side": "buy" if buy else "sell", "volume": p.volume,
                               "price_open": p.price_open, "price_now": now_price, "sl": p.sl,
                               "profit": p.profit + p.swap, "r": r})
    bot, strategy = settings.bot, settings.strategy
    return BotView(
        name=BOT_TITLES.get(strategy.name, strategy.name),
        description=f"{bot.timeframe} · {', '.join(bot.symbols)} · magic {magic} · modo {bot.mode} en el archivo",
        expected=settings.backtest,
        trades=closed_trades(gateway.bot_deals(magic, datetime.now() - timedelta(days=400)), info),
        open_positions=open_positions, events=events, status=liveness(last_beat, datetime.now()),
    )


def cmd_panel(args) -> None:
    from mt5bot.report import render

    gateway = connected_gateway()
    try:
        balance, equity = gateway.balance_and_equity()
        bots = [bot_view(gateway, load_settings(path)) for path in args.configs]
    finally:
        gateway.shutdown()
    PANEL_PATH.write_text(render(bots, balance, equity, datetime.now()), encoding="utf-8")
    print(f"panel guardado en {PANEL_PATH}")
    if not args.no_open:
        os.startfile(PANEL_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(prog="mt5bot")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="arranca el bot (respeta bot.mode)")
    # Permite probar en demo sin cambiar el dry_run por defecto del settings.toml; la cuenta real sigue bloqueada.
    run.add_argument("--mode", choices=["dry_run", "live"])
    run.set_defaults(func=cmd_run)

    download = commands.add_parser("download", help="descarga velas históricas de MT5 a CSV")
    download.add_argument("--symbol", required=True)
    download.add_argument("--timeframe", default="M15")
    download.add_argument("--days", type=int, default=730)
    download.set_defaults(func=cmd_download)

    backtest = commands.add_parser("backtest", help="corre la estrategia sobre un CSV")
    backtest.add_argument("--csv", type=Path, required=True)
    backtest.add_argument("--spec", type=Path, required=True)
    backtest.set_defaults(func=cmd_backtest)

    panel = commands.add_parser("panel", help="genera el panel HTML de los bots y lo abre en el navegador")
    panel.add_argument("--configs", type=Path, nargs="+",
                       default=[Path("config/settings.toml"), Path("config/rsi2.toml")])
    panel.add_argument("--no-open", action="store_true", help="solo genera el archivo")
    panel.set_defaults(func=cmd_panel)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
