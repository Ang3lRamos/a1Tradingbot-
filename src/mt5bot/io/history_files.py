import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from mt5bot.core.models import SymbolSpec


def save_history(bars: pd.DataFrame, spec: SymbolSpec, folder: Path, timeframe: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / f"{spec.name}_{timeframe}.csv"
    bars.to_csv(csv_path, index=False)
    (folder / f"{spec.name}_spec.json").write_text(json.dumps(asdict(spec), indent=2), encoding="utf-8")
    return csv_path


def load_bars(csv_path: Path) -> pd.DataFrame:
    bars = pd.read_csv(csv_path, parse_dates=["time"])
    return bars.sort_values("time").reset_index(drop=True)


def load_spec(spec_path: Path) -> SymbolSpec:
    return SymbolSpec(**json.loads(spec_path.read_text(encoding="utf-8")))
