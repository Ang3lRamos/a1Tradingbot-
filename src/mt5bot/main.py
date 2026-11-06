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

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
