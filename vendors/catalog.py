"""Fictional vendor counters/storefront logic shared by the FastAPI mock (vendors.app) and sal-tools fallback.

Stock and ETA are deterministic from vendor_catalog (SingleStore via db.client, or the fixture DB).
Orders persist to runs/vendors/orders.jsonl so the list page survives restarts.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta

from tools import context, data

_lock = threading.RLock()
PREFIX = {"mission": "MAS", "bayshore": "BPC", "partsdepot": "PDO"}


def _orders_file():
    return context.runs_dir() / "vendors" / "orders.jsonl"


def search(vendor_id: str, oem: str) -> list[dict]:
    rows, _ = data.query(
        "SELECT c.vendor_id, c.sku, c.vendor_part_no, c.oem_part_no, c.brand, c.description, c.price, "
        "c.qty_on_hand, c.eta_minutes, c.shopify_variant_id FROM vendor_catalog c "
        "WHERE c.vendor_id = %s AND (c.oem_part_no = %s OR c.oem_part_no LIKE %s) ORDER BY c.price",
        (vendor_id, oem, oem[:4] + "%" if len(oem) >= 6 else oem))  # counter search is fuzzy, like a real one
    cores, _ = data.query("SELECT core_charge FROM parts WHERE oem_part_no = %s", (oem,))
    core = float(cores[0]["core_charge"] or 0) if cores else 0.0
    out = []
    for r in rows:
        eta = int(r["eta_minutes"] or 0)
        out.append({"vendor_id": r["vendor_id"], "sku": r["sku"], "vendor_part_no": r["vendor_part_no"],
                    "oem_part_no": r["oem_part_no"], "brand": r["brand"], "desc": r["description"],
                    "price": float(r["price"]), "qty_on_hand": int(r["qty_on_hand"] or 0), "eta_minutes": eta,
                    "eta": context.plus_minutes(eta), "core_charge": core,
                    "shopify_variant_id": r.get("shopify_variant_id") or ""})
    return out


def _row(vendor_id: str, sku: str) -> dict | None:
    rows, _ = data.query("SELECT * FROM vendor_catalog WHERE vendor_id = %s AND sku = %s", (vendor_id, sku))
    return rows[0] if rows else None


def _order_id(vendor_id: str, key: str) -> str:
    with _lock:
        n = 1
        f = _orders_file()
        if f.exists():
            n += sum(1 for _ in f.open(encoding="utf-8"))
    h = hashlib.sha1(f"{key}|{n}".encode()).hexdigest()[:4].upper()
    return f"{PREFIX.get(vendor_id, vendor_id[:3].upper())}-{n:04d}{h}"


def place_many(vendor_id: str, items: list[tuple[str, int]], ro_id: str | None, sim_ts: str | None = None,
               run_id: str | None = None) -> dict:
    lines, total, eta_min = [], 0.0, 0
    for sku, qty in items:
        r = _row(vendor_id, sku)
        if not r:
            return {"error": {"code": "unknown_sku", "message": f"{vendor_id} has no sku {sku}"}}
        if int(r["qty_on_hand"] or 0) < qty:
            return {"error": {"code": "out_of_stock", "message": f"{vendor_id} has {r['qty_on_hand']} of {sku}"}}
        lines.append({"sku": sku, "qty": qty, "unit_price": float(r["price"]), "brand": r["brand"]})
        total += float(r["price"]) * qty
        eta_min = max(eta_min, int(r["eta_minutes"] or 0))
    base = datetime.fromisoformat(sim_ts) if sim_ts else context.now()
    order = {"order_id": _order_id(vendor_id, json.dumps(items) + str(ro_id)), "vendor_id": vendor_id,
             "ro_id": ro_id, "lines": lines, "total": round(total, 2),
             "placed_at": base.isoformat(), "eta": (base + timedelta(minutes=eta_min)).isoformat(),
             "run_id": run_id or context.run_id(), "status": "placed"}
    f = _orders_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    with _lock, f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(order) + "\n")
    return order


def place(vendor_id: str, sku: str, qty: int, ro_id: str | None, sim_ts: str | None = None,
          run_id: str | None = None) -> dict:
    return place_many(vendor_id, [(sku, int(qty))], ro_id, sim_ts=sim_ts, run_id=run_id)


def list_orders(vendor_id: str) -> list[dict]:
    f = _orders_file()
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("vendor_id") == vendor_id:
            out.append(o)
    return out
