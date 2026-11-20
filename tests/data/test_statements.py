import csv
from pathlib import Path

from seed.generate import build

ROOT = Path(__file__).resolve().parents[2]


def test_statement_reconciles_to_90():
    t = build()
    by_inv = {o["external_ref"]: o["order_id"] for o in t["orders"]}
    ph = {h["order_id"]: h for h in t["purchase_history"]}
    rows = list(csv.DictReader((ROOT / "seed/statements/bayshore_2026-11.csv").open(encoding="utf-8")))
    missing = [ph[by_inv[r["invoice_no"]]]["core_credit_due"] - float(r["core_credit"]) for r in rows]
    assert round(sum(m for m in missing if m > 0), 2) == 90.0
    assert sum(1 for m in missing if m > 0) == 2
    for ext in ("pdf", "csv"):
        assert (ROOT / f"seed/statements/bayshore_2026-11.{ext}").stat().st_size > 500
    assert (ROOT / "seed/statements/bayshore_2026-11_scan.png").exists()
