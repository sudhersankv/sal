"""SIE-encode vendor_catalog listings -> vendor_catalog.embedding (normalized, JSON array).

Embedding text = brand + vendor part no + description. Writes only when SIE is live (never stores
fallback vectors in SingleStore). Prints the model id and vector dim (lead: put dim in db.sql).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path

from db.client import get_db, vec_to_json


def listing_text(r: dict) -> str:
    return f"{r['brand']} {r['vendor_part_no']} | {r['description']}"


CACHE = Path(__file__).parent / "cache" / "sie_embeddings.json.gz"  # {sha1(text): [floats]} for offline/replay


def _key(t: str) -> str:
    return hashlib.sha1(t.encode()).hexdigest()


def _cache() -> dict:
    return json.loads(gzip.decompress(CACHE.read_bytes())) if CACHE.exists() else {}


def _save(c: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(gzip.compress(json.dumps(c, separators=(",", ":")).encode()))


def main() -> int:
    from tools.integrations import sie

    db = get_db()
    cache = _cache()
    if cache:  # cached SIE vectors first (committed; same model as embedding_meta.json)
        rows = db.query("SELECT vendor_id, sku, vendor_part_no, brand, description FROM vendor_catalog "
                        "WHERE embedding IS NULL")
        hit = [(json.dumps(cache[_key(listing_text(x))]), x["vendor_id"], x["sku"]) for x in rows
               if _key(listing_text(x)) in cache]
        if hit:
            db.executemany("UPDATE vendor_catalog SET embedding=%s WHERE vendor_id=%s AND sku=%s", hit)
            print(f"sie: {len(hit)} embeddings from seed cache")
    if not sie.available():
        print("SKIP sie: no key")
        return 0
    os.environ.setdefault("SIE_PROVISION_TIMEOUT", "600")
    rows = db.query("SELECT vendor_id, sku, vendor_part_no, brand, description FROM vendor_catalog "
                    "WHERE embedding IS NULL ORDER BY vendor_id, sku")
    if not rows:
        print("sie: all listings already embedded")
        return 0
    col_dim = db.vector_dim() if hasattr(db, "vector_dim") else None
    done = 0
    for i in range(0, len(rows), 32):
        batch = rows[i:i + 32]
        r = sie.embed([listing_text(x) for x in batch])
        if r.get("source") == "fallback" or "error" in r:
            print(f"sie embed not live ({r.get('model') or r.get('error')}); stopping, {done} embedded")
            return 0
        if col_dim and r["dim"] != col_dim:
            print(f"sie dim {r['dim']} != vendor_catalog VECTOR({col_dim}); ask lead to change db.sql. stopping")
            return 1
        db.executemany("UPDATE vendor_catalog SET embedding=%s WHERE vendor_id=%s AND sku=%s",
                       [(vec_to_json(v), x["vendor_id"], x["sku"]) for v, x in zip(r["vectors"], batch)])
        for v, x in zip(r["vectors"], batch):
            cache[_key(listing_text(x))] = [round(float(f), 5) for f in v]
        _save(cache)
        done += len(batch)
        print(f"sie: embedded {done}/{len(rows)} model={r['model']} dim={r['dim']}", flush=True)
    meta = {"model": r["model"], "dim": r["dim"], "rows": done}
    (__import__("pathlib").Path(__file__).with_name("embedding_meta.json")).write_text(json.dumps(meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
