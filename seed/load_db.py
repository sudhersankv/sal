"""Load the generated seed into the active DB backend (idempotent: replaces seed rows).

    python -m seed.load_db [--reset]

Keeps embeddings and Shopify variant ids already loaded (so re-running doesn't wipe
seed.load_embeddings / seed.load_shopify work).
"""
from __future__ import annotations

import argparse
import json

from db.client import DB, get_db
from db.migrate import migrate
from seed.generate import build

# tables fully owned by the seed (cleared + reloaded). Run-time tables (metrics, approvals,
# payments, verifications, statement_lines) are left alone except by --reset.
SEED_TABLES = ["vendors", "parts", "fitments", "part_brands", "vendor_catalog", "inventory", "bookings",
               "customers", "repair_orders", "orders", "order_lines", "purchase_history", "rules", "facts"]
RUNTIME_TABLES = ["metrics", "approvals", "payments", "verifications", "statement_lines"]


def _cell(v):
    return json.dumps(v) if isinstance(v, (list, dict)) else v


def insert_rows(db: DB, table: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    cols = list(rows[0])
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})"
    db.executemany(sql, [tuple(_cell(r[c]) for c in cols) for r in rows])
    return len(rows)


def load(db: DB | None = None, reset: bool = False) -> dict[str, int]:
    db = db or get_db()
    migrate(db)
    tables = build()
    keep = {}
    if not reset:
        for r in db.query("SELECT vendor_id, sku, shopify_variant_id, embedding FROM vendor_catalog "
                          "WHERE shopify_variant_id IS NOT NULL OR embedding IS NOT NULL"):
            keep[(r["vendor_id"], r["sku"])] = r
    # never delete seed-created ROs above history range (sim creates RO-1042+); only seed ones
    for t in SEED_TABLES:
        if t == "repair_orders":
            ids = [r["ro_id"] for r in tables[t]]
            db.executemany("DELETE FROM repair_orders WHERE ro_id = %s", [(i,) for i in ids])
        elif t in ("orders", "order_lines", "purchase_history"):
            ids = [(r["order_id"],) for r in tables["orders"]]
            db.executemany(f"DELETE FROM {t} WHERE order_id = %s", ids)
        elif t == "rules":
            db.executemany("DELETE FROM rules WHERE rule_id = %s", [(r["rule_id"],) for r in tables[t]])
        elif t == "facts":
            db.execute("DELETE FROM facts WHERE source = 'seed'")
        else:
            db.execute(f"DELETE FROM {t}")
    if reset:
        for t in RUNTIME_TABLES:
            db.execute(f"DELETE FROM {t}")
    counts = {t: insert_rows(db, t, tables[t]) for t in SEED_TABLES}
    for (vid, sku), r in keep.items():
        if r.get("shopify_variant_id"):
            db.execute("UPDATE vendor_catalog SET shopify_variant_id=%s WHERE vendor_id=%s AND sku=%s",
                       (r["shopify_variant_id"], vid, sku))
    if keep and db.backend == "sqlite":  # singlestore returns VECTOR as bytes; re-run load_embeddings there
        for (vid, sku), r in keep.items():
            if r.get("embedding"):
                db.execute("UPDATE vendor_catalog SET embedding=%s WHERE vendor_id=%s AND sku=%s",
                           (json.dumps(r["embedding"]) if not isinstance(r["embedding"], str) else r["embedding"],
                            vid, sku))
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="also clear run-time tables")
    a = ap.parse_args()
    db = get_db()
    counts = load(db, reset=a.reset)
    print(f"load_db: backend={db.backend} " + " ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
