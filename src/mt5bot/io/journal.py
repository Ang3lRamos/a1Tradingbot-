"""Bitácora en SQLite: cada señal, bloqueo, orden y cierre, con su motivo."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    logged_at TEXT NOT NULL,
    server_time TEXT,
    symbol TEXT,
    kind TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    ticket INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry REAL NOT NULL,
    initial_stop REAL NOT NULL,
    target REAL NOT NULL,
    lots REAL NOT NULL,
    risk_money REAL NOT NULL,
    opened_at TEXT NOT NULL
);
"""


class Journal:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def log(self, kind: str, detail: dict, symbol: str | None = None, server_time: datetime | None = None):
        self.db.execute(
            "INSERT INTO events (logged_at, server_time, symbol, kind, detail) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"),
             server_time.isoformat() if server_time else None,
             symbol, kind, json.dumps(detail, default=str, ensure_ascii=False)),
        )
        self.db.commit()

    def record_position(self, ticket: int, plan, opened_at: datetime):
        signal = plan.signal
        self.db.execute(
            "INSERT OR REPLACE INTO positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ticket, signal.symbol, signal.side, signal.entry, signal.stop, signal.target,
             plan.lots, plan.risk_money, opened_at.isoformat()),
        )
        self.db.commit()

    def initial_stop(self, ticket: int) -> float | None:
        row = self.db.execute("SELECT initial_stop FROM positions WHERE ticket = ?", (ticket,)).fetchone()
        return row[0] if row else None

    def positions_info(self) -> dict[int, dict]:
        """Riesgo y stop inicial de cada posición que abrió el bot, por ticket."""
        rows = self.db.execute("SELECT ticket, symbol, side, entry, initial_stop, risk_money, opened_at FROM positions")
        return {t: {"symbol": s, "side": side, "entry": e, "initial_stop": st, "risk_money": r, "opened_at": o}
                for t, s, side, e, st, r, o in rows}

    def recent_events(self, limit: int) -> list[dict]:
        rows = self.db.execute("SELECT logged_at, server_time, symbol, kind, detail FROM events ORDER BY id DESC LIMIT ?",
                               (limit,))
        return [{"logged_at": la, "server_time": st, "symbol": s, "kind": k, "detail": json.loads(d)}
                for la, st, s, k, d in rows]

    def opened_at(self, ticket: int) -> datetime | None:
        row = self.db.execute("SELECT opened_at FROM positions WHERE ticket = ?", (ticket,)).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def close(self):
        self.db.close()
