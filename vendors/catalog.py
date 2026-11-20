"""Fictional vendor counters/storefront logic shared by the FastAPI mock (vendors.app) and sal-tools fallback.

Stock and ETA are deterministic from vendor_catalog (SingleStore via db.client, or the fixture DB).
Orders persist to runs/vendors/orders.jsonl so the list page survives restarts.
"""
from __future__ import annotations

import hashlib
import json
import re
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


def _alnum(v) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(v or "").upper())


def resolve(vendor_id: str | None, ident: str) -> dict | None:
    """Catalog row for whatever identifier a caller has: sku, vendor_part_no, Shopify variant id, or (if it
    names exactly one in-stock listing at the vendor) the OEM number. Case/punctuation-insensitive.
    Returns {"error": ...} when an OEM number is ambiguous so the caller can ask for a sku."""
    ident = str(ident or "").strip()
    if not ident:
        return None
    where, params = ("vendor_id = %s", [vendor_id]) if vendor_id else ("1 = 1", [])
    rows, _ = data.query(f"SELECT * FROM vendor_catalog WHERE {where} AND (sku = %s OR vendor_part_no = %s OR "
                         "shopify_variant_id = %s)", (*params, ident, ident, ident))
    if rows:
        return rows[0]
    key = _alnum(ident)
    allrows, _ = data.query(f"SELECT * FROM vendor_catalog WHERE {where}", tuple(params))
    for col in ("sku", "vendor_part_no", "shopify_variant_id"):
        hit = [r for r in allrows if key and _alnum(r.get(col)) == key]
        if hit:
            return hit[0]
    # brand part no. inside vendor_part_no (e.g. "GL-8772" vs "MOT-GL8772")
    hit = [r for r in allrows if len(key) >= 4 and _alnum(r.get("vendor_part_no")).endswith(key)]
    if len(hit) == 1:
        return hit[0]
    oem = [r for r in allrows if _alnum(r.get("oem_part_no")) == key]
    if len(oem) == 1:
        return oem[0]
    if len(oem) > 1:
        opts = ", ".join(f"{r['sku']} ({r['brand']} ${float(r['price']):.2f})" for r in oem)
        return {"error": {"code": "ambiguous_part", "message": f"{ident} matches {len(oem)} listings at "
                          f"{vendor_id}: {opts}. Pass the sku."}}
    return None


def _row(vendor_id: str, sku: str) -> dict | None:
    r = resolve(vendor_id, sku)
    return r if r and "error" not in r else None


def _order_id(vendor_id: str, key: str) -> str:
    with _lock:
        n = 1
        f = _orders_file()
        if f.exists():
            n += sum(1 for _ in f.open(encoding="utf-8"))
    h = hashlib.sha1(f"{key}|{n}".encode()).hexdigest()[:4].upper()
    return f"{PREFIX.get(vendor_id, vendor_id[:3].upper())}-{n:04d}{h}"


def shop_now(run_id: str | None = None) -> datetime:
    """Simulated shop clock for callers that don't send sim_ts: the run's (or newest run's) last event ts,
    else env SAL_SIM_TS / context default. Never the mock process's own idea of 'now'."""
    import os
    if os.environ.get("SAL_SIM_TS") or not run_id and os.environ.get("SAL_RUN_ID"):
        return context.now()
    try:
        root = context.runs_dir()
        cands = [root / run_id / "events.jsonl"] if run_id else sorted(
            root.glob("*/events.jsonl"), key=lambda q: q.stat().st_mtime, reverse=True)[:1]
        for f in cands:
            if f.exists():
                last = f.read_text(encoding="utf-8").strip().splitlines()[-1]
                return datetime.fromisoformat(json.loads(last)["ts"])
    except Exception:
        pass
    return context.now()


def place_many(vendor_id: str, items: list[tuple[str, int]], ro_id: str | None, sim_ts: str | None = None,
               run_id: str | None = None) -> dict:
    lines, total, eta_min = [], 0.0, 0
    for ident, qty in items:
        r = resolve(vendor_id, ident)
        if r and "error" in r:
            return r
        if not r:
            return {"error": {"code": "unknown_sku", "message": f"{vendor_id} has no part {ident} (pass the sku "
                              "from search_vendor)"}}
        sku = r["sku"]
        if int(r["qty_on_hand"] or 0) < qty:
            return {"error": {"code": "out_of_stock", "message": f"{vendor_id} has {r['qty_on_hand']} of {sku}"}}
        lines.append({"sku": sku, "qty": qty, "unit_price": float(r["price"]), "brand": r["brand"]})
        total += float(r["price"]) * qty
        eta_min = max(eta_min, int(r["eta_minutes"] or 0))
    base = datetime.fromisoformat(sim_ts) if sim_ts else shop_now(run_id)
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
