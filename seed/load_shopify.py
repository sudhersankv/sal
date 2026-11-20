"""Create PartsDepot consumables on the Shopify dev store; store variant GIDs in vendor_catalog.

Idempotent: looks a variant up by SKU before creating. Token via db/shopify_auth.py
(client-credentials grant). Products are the PartsDepot listings for inventory SKUs that are
consumables (filters, wipers, fluids, bulbs, brake cleaner).
"""
from __future__ import annotations

import json
from pathlib import Path

from db.client import get_db
from db.shopify_auth import available, get_token, gql

OUT = Path(__file__).with_name("shopify_variants.json")
TYPES = ("oil_filter", "wiper_blade", "brake_cleaner", "cabin_air_filter", "engine_air_filter", "atf", "coolant", "bulb")

FIND = """query($q: String!) { productVariants(first: 1, query: $q) { nodes { id sku product { id } } } }"""
CREATE = """mutation($p: ProductCreateInput!) { productCreate(product: $p) {
  product { id variants(first: 1) { nodes { id } } } userErrors { field message } } }"""
UPDATE = """mutation($pid: ID!, $v: [ProductVariantsBulkInput!]!) { productVariantsBulkUpdate(productId: $pid, variants: $v) {
  productVariants { id sku price } userErrors { field message } } }"""


def products(db) -> list[dict]:
    return db.query(
        "SELECT c.sku, c.brand, c.vendor_part_no, c.description, c.price, i.part_type, i.name FROM vendor_catalog c "
        "JOIN inventory i ON i.sku = c.sku WHERE c.vendor_id='partsdepot' AND i.part_type IN ("
        + ",".join(["%s"] * len(TYPES)) + ") ORDER BY i.part_type, c.sku", TYPES)


def upsert(p: dict) -> str | None:
    r = gql(FIND, {"q": f"sku:{p['sku']}"})
    nodes = (r.get("data") or {}).get("productVariants", {}).get("nodes", []) if "error" not in r else []
    if nodes and nodes[0].get("sku") == p["sku"]:
        return nodes[0]["id"]
    r = gql(CREATE, {"p": {"title": p["name"], "vendor": p["brand"], "productType": p["part_type"],
                           "descriptionHtml": p["description"], "tags": ["sal-seed", p["part_type"]],
                           "status": "ACTIVE"}})
    if "error" in r:
        print(f"shopify create {p['sku']}: {r['error']}")
        return None
    res = r["data"]["productCreate"]
    if res["userErrors"]:
        print(f"shopify create {p['sku']}: {res['userErrors']}")
        return None
    pid, vid = res["product"]["id"], res["product"]["variants"]["nodes"][0]["id"]
    r = gql(UPDATE, {"pid": pid, "v": [{"id": vid, "price": f"{p['price']:.2f}",
                                         "inventoryItem": {"sku": p["sku"], "tracked": False}}]})
    errs = (r.get("data") or {}).get("productVariantsBulkUpdate", {}).get("userErrors") if "error" not in r else r
    if errs:
        print(f"shopify price/sku {p['sku']}: {errs}")
    return vid


def main() -> int:
    if not available():
        print("SKIP shopify: no key (place_shopify_order uses the mock online vendor)")
        return 0
    if not get_token():
        print("SKIP shopify: token exchange failed (check app install + scopes)")
        return 0
    db = get_db()
    out = {}
    for p in products(db):
        vid = upsert(p)
        if vid:
            out[p["sku"]] = vid
            db.execute("UPDATE vendor_catalog SET shopify_variant_id=%s WHERE vendor_id='partsdepot' AND sku=%s",
                       (vid, p["sku"]))
    OUT.write_text(json.dumps(out, indent=1))
    print(f"shopify: {len(out)} variants linked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
