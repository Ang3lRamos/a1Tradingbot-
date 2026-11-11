"""Convierte research/registry.csv en web/src/research/registry.json para la interfaz.

Uso (desde la raíz del repo): python web/scripts/registry_to_json.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
rows = []
for r in csv.DictReader((ROOT / "research" / "registry.csv").open(encoding="utf-8")):
    result = json.loads(r["resultado"])
    rows.append({
        "date": r["fecha"][:10],
        "family": r["hipotesis"],
        "variant": r["variante"],
        "period": r["periodo"],
        "p": float(r["p_azar"]) if r["p_azar"] else None,
        **{k: v for k, v in result.items() if isinstance(v, (int, float))},
    })
out = ROOT / "web" / "src" / "research" / "registry.json"
out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{out.relative_to(ROOT)}: {len(rows)} pruebas")
