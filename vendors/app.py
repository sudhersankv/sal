"""Mock vendor counters + online store (fictional companies). `uvicorn vendors.app:app --port 8101`."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from tools import data
from vendors import catalog

app = FastAPI(title="Sal mock vendors (fictional)")


class OrderIn(BaseModel):
    sku: str | None = None
    qty: int = 1
    lines: list[dict] | None = None  # [{sku|variant_id, qty}] for the online store
    ro_id: str | None = None
    run_id: str | None = None
    sim_ts: str | None = None
    note: str | None = None


def _vendor_or_404(vendor_id: str) -> dict:
    rows, _ = data.query("SELECT * FROM vendors WHERE vendor_id = %s", (vendor_id,))
    if not rows:
        raise HTTPException(404, f"unknown vendor {vendor_id}")
    return rows[0]


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/v/{vendor_id}/search")
def search(vendor_id: str, oem: str):
    _vendor_or_404(vendor_id)
    return {"vendor_id": vendor_id, "listings": catalog.search(vendor_id, oem)}


@app.post("/v/{vendor_id}/orders")
def place(vendor_id: str, body: OrderIn):
    _vendor_or_404(vendor_id)
    if body.lines:
        items = []
        for ln in body.lines:
            key = ln.get("sku") or ln.get("variant_id") or ""
            rows, _ = data.query("SELECT sku FROM vendor_catalog WHERE vendor_id = %s AND (sku = %s OR "
                                 "shopify_variant_id = %s)", (vendor_id, key, key))
            items.append((rows[0]["sku"] if rows else key, int(ln.get("qty") or 1)))
    elif body.sku:
        items = [(body.sku, body.qty)]
    else:
        raise HTTPException(422, "sku or lines required")
    res = catalog.place_many(vendor_id, items, body.ro_id, sim_ts=body.sim_ts, run_id=body.run_id)
    if "error" in res:
        raise HTTPException(409, res["error"]["message"])
    return res


@app.get("/v/{vendor_id}/orders")
def orders(vendor_id: str, format: str = "json"):
    v = _vendor_or_404(vendor_id)
    rows = catalog.list_orders(vendor_id)
    if format != "html":
        return {"vendor_id": vendor_id, "orders": rows}
    trs = "".join(f"<tr><td>{o['order_id']}</td><td>{o.get('ro_id') or ''}</td><td>{o['placed_at'][:16]}</td>"
                  f"<td>{o['eta'][:16]}</td><td>${o['total']:.2f}</td></tr>" for o in reversed(rows))
    return HTMLResponse(f"<h2>{v['name']} (fictional) — orders</h2><table border=1 cellpadding=4>"
                        f"<tr><th>Order</th><th>RO</th><th>Placed</th><th>ETA</th><th>Total</th></tr>{trs}</table>")
