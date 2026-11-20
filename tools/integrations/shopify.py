"""Shopify Admin GraphQL (SPEC §8.7): client-credentials token → products / draftOrderCreate → draftOrderComplete.

Token: POST https://{shop}/admin/oauth/access_token (grant_type=client_credentials, client_id, client_secret).
GraphQL: POST https://{shop}/admin/api/{version}/graphql.json, header X-Shopify-Access-Token.
Fallback: mock online vendor POST {VENDORS_URL}/v/partsdepot/orders.
"""

from __future__ import annotations

import time

import httpx

from ._common import cache_put, cached_call, env, err, has, key_for, log, safe_exc

SERVICE = "shopify"
_token: dict = {}


def available() -> bool:
    return has("SHOPIFY_SHOP", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET")


def _shop() -> str:
    s = env("SHOPIFY_SHOP").replace("https://", "").replace("http://", "").strip("/")
    return s


def _version() -> str:
    return env("SHOPIFY_API_VERSION", "2026-10")


def get_token() -> str | None:
    if not available():
        return None
    if _token.get("v") and _token.get("exp", 0) > time.time() + 60:
        return _token["v"]
    try:
        r = httpx.post(
            f"https://{_shop()}/admin/oauth/access_token",
            data={
                "grant_type": "client_credentials",
                "client_id": env("SHOPIFY_CLIENT_ID"),
                "client_secret": env("SHOPIFY_CLIENT_SECRET"),
            },
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if r.status_code >= 400:
            log(f"[shopify] token http_{r.status_code}")
            return None
        j = r.json()
        _token["v"] = j.get("access_token")
        _token["exp"] = time.time() + float(j.get("expires_in") or 3600)
        return _token["v"]
    except Exception as e:
        log(f"[shopify] token failed: {safe_exc(e)}")
        return None


def gql(query: str, variables: dict | None = None) -> dict:
    tok = get_token()
    if not tok:
        return err("no_token", "shopify token unavailable")
    r = httpx.post(
        f"https://{_shop()}/admin/api/{_version()}/graphql.json",
        headers={"X-Shopify-Access-Token": tok, "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=45,
    )
    if r.status_code >= 400:
        return err(f"http_{r.status_code}", r.text[:300])
    j = r.json()
    if j.get("errors"):
        return err("graphql", str(j["errors"])[:300])
    return j.get("data") or {}


PRODUCTS_Q = """
query($first:Int!){ products(first:$first){ nodes{ id title
  variants(first:20){ nodes{ id sku price inventoryQuantity } } } } }
"""


def products(first: int = 50) -> dict:
    def live():
        d = gql(PRODUCTS_Q, {"first": first})
        if "error" in d:
            return d
        out = []
        for p in d.get("products", {}).get("nodes", []):
            out.append(
                {
                    "id": p["id"],
                    "title": p["title"],
                    "variants": [
                        {"id": v["id"], "sku": v.get("sku"), "price": float(v.get("price") or 0), "inventory_quantity": v.get("inventoryQuantity")}
                        for v in p.get("variants", {}).get("nodes", [])
                    ],
                }
            )
        return {"products": out}

    def fb():
        try:
            r = httpx.get(f"{_vendors_url()}/v/partsdepot/catalog", timeout=5)
            if r.status_code < 400:
                return {"products": r.json() if isinstance(r.json(), list) else r.json().get("listings", []), "source": "fallback"}
        except Exception:
            pass
        return {"products": [], "source": "fallback"}

    return cached_call(SERVICE, key_for("products", first), live if available() else None, fb)


CREATE_M = """
mutation($input: DraftOrderInput!){ draftOrderCreate(input:$input){
  draftOrder{ id totalPriceSet{ shopMoney{ amount } } } userErrors{ field message } } }
"""
COMPLETE_M = """
mutation($id: ID!){ draftOrderComplete(id:$id, paymentPending:true){
  draftOrder{ id order{ id name legacyResourceId totalPriceSet{ shopMoney{ amount } } } }
  userErrors{ field message } } }
"""


def _vendors_url() -> str:
    return env("VENDORS_URL", "http://localhost:8101").rstrip("/")


def _admin_url(order_legacy_id: str | None) -> str:
    handle = _shop().split(".")[0]
    return f"https://admin.shopify.com/store/{handle}/orders/{order_legacy_id}" if order_legacy_id else ""


def _fallback_order(lines: list[dict], note: str) -> dict:
    try:
        r = httpx.post(
            f"{_vendors_url()}/v/partsdepot/orders",
            json={"lines": lines, "note": note, "channel": "online"},
            timeout=10,
        )
        if r.status_code >= 400:
            return err(f"mock_http_{r.status_code}", r.text[:200], source="fallback")
        j = r.json()
        return {
            "shopify_order_id": j.get("order_id") or j.get("id"),
            "admin_url": j.get("admin_url", ""),
            "total": float(j.get("total") or 0),
            "draft_order_id": None,
            "eta": j.get("eta"),
            "source": "fallback",
            "label": "PartsDepot Online (mock — Shopify not configured)",
        }
    except Exception as e:
        return err("mock_unreachable", safe_exc(e), source="fallback")


def place_order(lines: list[dict], note: str = "") -> dict:
    """lines: [{"variant_id": "gid://shopify/ProductVariant/..", "qty": int}]. Not cached (side effect)."""
    if not available():
        return _fallback_order(lines, note)
    try:
        inp = {"lineItems": [{"variantId": ln["variant_id"], "quantity": int(ln.get("qty", 1))} for ln in lines], "note": note}
        d = gql(CREATE_M, {"input": inp})
        if "error" in d:
            raise RuntimeError(d["error"]["message"])
        res = d["draftOrderCreate"]
        if res.get("userErrors"):
            raise RuntimeError(str(res["userErrors"])[:200])
        draft_id = res["draftOrder"]["id"]
        d2 = gql(COMPLETE_M, {"id": draft_id})
        if "error" in d2:
            raise RuntimeError(d2["error"]["message"])
        res2 = d2["draftOrderComplete"]
        if res2.get("userErrors"):
            raise RuntimeError(str(res2["userErrors"])[:200])
        order = (res2.get("draftOrder") or {}).get("order") or {}
        out = {
            "shopify_order_id": order.get("id"),
            "order_name": order.get("name"),
            "admin_url": _admin_url(order.get("legacyResourceId")),
            "total": float(((order.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount") or 0),
            "draft_order_id": draft_id,
            "source": "live",
        }
        cache_put(SERVICE, key_for("order", lines, note, time.time()), out)
        return out
    except Exception as e:
        log(f"[shopify] live order failed, using mock vendor: {safe_exc(e)}")
        out = _fallback_order(lines, note)
        out["warning"] = f"shopify failed: {safe_exc(e)[:120]}"
        return out
