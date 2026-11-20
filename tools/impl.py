"""sal-tools implementations (contracts/tools.md). Plain functions: dict in, dict out, never raise.

Each tool tries the real backend (db.client / tools.integrations.* / public API) and falls back to the
fixture world in tools/fixtures.py, so the hero week always runs. Output carries `backend`/`method`
fields so the README/UI can label what was real vs fallback.
"""
from __future__ import annotations

import csv
import functools
import hashlib
import io
import json
import logging
import math
import os
import re
from datetime import timedelta
from pathlib import Path

from tools import backends, context, data, events, policy
from tools import fixtures as fx

log = logging.getLogger("sal-tools")
ROOT = Path(__file__).resolve().parents[1]
VENDOR_URL = os.environ.get("SAL_VENDORS_URL", "http://localhost:8101")


# --------------------------------------------------------------------------------------------- helpers
def safe(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:  # noqa: BLE001
            log.exception("tool %s failed", fn.__name__)
            events.emit("error", f"{fn.__name__} failed: {type(e).__name__}"[:140], actor="system",
                        reason=str(e)[:280], data={"tool": fn.__name__})
            return {"error": {"code": "internal", "message": f"{type(e).__name__}: {e}"[:500]}}
    return wrapper


def err(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


_MOCK_STATE = {"up": None, "checked": 0.0}


def _mock_up() -> bool:
    """Is the vendors/ mock (port 8101) reachable? Cached 30s so a down mock costs one fast probe, not 3s/call."""
    import time
    if _MOCK_STATE["up"] is not None and time.time() - _MOCK_STATE["checked"] < 30:
        return bool(_MOCK_STATE["up"])
    try:
        import httpx
        up = httpx.get(f"{VENDOR_URL}/health", timeout=0.5).status_code == 200
    except Exception:
        up = False
    _MOCK_STATE.update(up=up, checked=time.time())
    return up


def _cache_path(kind: str, key: str) -> Path:
    h = hashlib.sha256(key.encode()).hexdigest()[:24]
    return context.runs_dir() / "cache" / kind / f"{h}.json"


def _cache_get(kind: str, key: str):
    for p in (_cache_path(kind, key), ROOT / "seed" / "cache" / kind / _cache_path(kind, key).name):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def _cache_put(kind: str, key: str, value) -> None:
    try:
        p = _cache_path(kind, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding="utf-8")
    except Exception:
        pass


def _http_get_json(url: str, timeout: float = 8.0):
    import httpx
    r = httpx.get(url, timeout=timeout, headers={"User-Agent": "sal-tools/0.1"})
    r.raise_for_status()
    return r.json()


def _num(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _catalog_row(vendor_id: str | None, sku: str) -> dict | None:
    if vendor_id:
        rows, _ = data.query("SELECT * FROM vendor_catalog WHERE vendor_id = %s AND sku = %s", (vendor_id, sku))
    else:
        rows, _ = data.query("SELECT * FROM vendor_catalog WHERE sku = %s OR shopify_variant_id = %s", (sku, sku))
    return rows[0] if rows else None


def _part_by_oem(oem: str) -> dict | None:
    rows, _ = data.query("SELECT * FROM parts WHERE oem_part_no = %s", (oem,))
    return rows[0] if rows else None


def _vendor(vendor_id: str) -> dict:
    rows, _ = data.query("SELECT * FROM vendors WHERE vendor_id = %s", (vendor_id,))
    return rows[0] if rows else {"vendor_id": vendor_id, "name": vendor_id, "kind": "counter"}


def _ledger(kind: str, rec: dict) -> None:
    p = context.runs_dir() / context.run_id() / "ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": kind, "ts": context.ts(), **rec}, default=str) + "\n")


def _short_id(prefix: str, *parts) -> str:
    h = hashlib.sha1(("|".join(map(str, parts)) + context.run_id()).encode()).hexdigest()[:8]
    return f"{prefix}_{h}"


# ------------------------------------------------------------------------------------------- NHTSA
@safe
def decode_vin(vin: str) -> dict:
    """Decode a VIN with NHTSA vPIC (tools.integrations.nhtsa: seed cache -> live -> runs cache)."""
    vin = (vin or "").strip().upper()
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json"
    raw = backends.call("nhtsa", ("decode_vin",), vin)
    if isinstance(raw, dict) and raw.get("make") and raw.get("year"):
        out = {**raw, "raw_source_url": raw.get("raw_source_url") or url, "method": raw.get("source", "nhtsa")}
    elif vin in fx.VIN_DECODES:
        out = {**fx.VIN_DECODES[vin], "method": "fixture"}
    else:
        return err("vin_not_decoded", (raw or {}).get("error", {}).get("message") or f"NHTSA could not decode {vin}")
    out.pop("source", None)
    events.emit("part.identified", f"VIN decoded: {out['year']} {str(out['make']).title()} {out['model']} {out['engine_l']}L",
                sources=[{"name": "NHTSA", "ref": "vPIC decodevinvalues", "url": out["raw_source_url"]}],
                refs={"vin": vin}, data={"partial": True, "vehicle": out})
    return out


@safe
def get_complaints(make: str, model: str, year: int, component_keyword: str = "") -> dict:
    """NHTSA complaints for the vehicle (context on known failure patterns of the CAR, not part brands)."""
    kw = (component_keyword or "").lower()
    raw = backends.call("nhtsa", ("complaints",), make, model, int(year), kw or None, 3)
    if isinstance(raw, dict) and "total" in raw:
        out = {"total": raw["total"], "matching": raw.get("matching", 0), "top": raw.get("top", [])[:3],
               "source_url": raw.get("source_url", ""), "method": raw.get("source", "nhtsa")}
    else:
        out = {**fx.COMPLAINTS_CIVIC_2014, "method": "fixture"}
    events.emit("context.retrieved", f"NHTSA: {out['matching']} of {out['total']} complaints mention '{kw or 'any'}'",
                reason="Vehicle failure-pattern context only; brand quality comes from shop history.",
                sources=[{"name": "NHTSA", "ref": "complaintsByVehicle", "url": out["source_url"]}],
                data={"kind": "complaints", "matching": out["matching"]})
    return out


# ------------------------------------------------------------------------------------------- Senso
@safe
def get_shop_rules(question: str) -> dict:
    """Ask the shop's rules (Senso POST /org/search). Cites content_ids."""
    raw = backends.call("senso", ("search",), question)
    if isinstance(raw, dict) and (raw.get("passages") or raw.get("answer")):
        out = {"answer": raw.get("answer") or "",
               "passages": [{"content_id": str(r.get("content_id", "")), "title": r.get("title", ""),
                             "chunk_text": (r.get("chunk_text") or "")[:600]} for r in raw.get("passages", [])[:5]],
               "method": raw.get("source", "senso")}
    else:
        hits = fx.SHOP_RULES
        out = {"answer": " ".join(d["chunk_text"] for d in hits[:4]), "passages": hits[:5], "method": "fixture"}
    ids = [p["content_id"] for p in out["passages"]][:5]
    events.emit("context.retrieved", f"Shop rules: {question}"[:140], reason=(out["answer"] or "")[:280],
                sources=[{"name": "Senso", "ref": i or p["title"]} for i, p in zip(ids, out["passages"])],
                data={"kind": "shop_rules", "question": question, "content_ids": ids, "method": out["method"]})
    return out


# ------------------------------------------------------------------------------------- part lookup
_DTC_POSITION = {"P0141": "downstream", "P0137": "downstream", "P0138": "downstream", "P0140": "downstream",
                 "P0135": "upstream", "P0131": "upstream", "P0132": "upstream", "P0133": "upstream"}


@safe
def identify_part(year: int, make: str, model: str, engine_l: float, dtc: str | None = None,
                  symptom: str | None = None) -> dict:
    """Fitment lookup (SingleStore fitments+parts): which OEM part fixes this DTC on this car."""
    rows, backend = data.query(
        "SELECT p.oem_part_no, p.part_type, p.position, p.description, p.has_core, p.core_charge, "
        "f.notes, f.dtc, f.engine_l FROM fitments f JOIN parts p ON p.part_id = f.part_id "
        "WHERE UPPER(f.make) = UPPER(%s) AND UPPER(f.model) = UPPER(%s) AND f.year = %s",
        (make, model, int(year)))
    rows = [r for r in rows if not engine_l or not r.get("engine_l") or abs(_num(r["engine_l"]) - _num(engine_l)) < 0.06]
    if not rows:
        return err("no_fitment", f"No fitment for {year} {make} {model} {engine_l}L")
    dtc = (dtc or "").upper().strip()
    best = [r for r in rows if dtc and (r.get("dtc") or "").upper() == dtc]
    if not best and dtc in _DTC_POSITION:
        best = [r for r in rows if (r.get("position") or "") == _DTC_POSITION[dtc]]
    if not best and symptom:
        s = symptom.lower()
        best = [r for r in rows if any(w in (r.get("description") or "").lower() for w in s.split() if len(w) > 3)]
    pick = (best or rows)[0]
    out = {"oem_part_no": pick["oem_part_no"], "part_type": pick["part_type"], "position": pick.get("position") or "",
           "notes": pick.get("notes") or "", "candidates": [
               {"oem_part_no": r["oem_part_no"], "part_type": r["part_type"], "position": r.get("position") or "",
                "description": r.get("description") or ""} for r in rows],
           "description": pick.get("description") or "", "core_charge": _num(pick.get("core_charge")),
           "backend": backend}
    events.emit("part.identified",
                f"{dtc + ' → ' if dtc else ''}{out['position'] + ' ' if out['position'] else ''}{out['part_type'].replace('_', ' ')}, OEM {out['oem_part_no']}"[:140],
                reason=out["notes"][:280] or None,
                sources=[{"name": "SingleStore", "ref": "fitments+parts"}],
                refs={"part_no": out["oem_part_no"]}, data={"vehicle": f"{year} {make} {model} {engine_l}L", "dtc": dtc})
    return out


@safe
def search_vendor(vendor_id: str, oem_part_no: str) -> dict:
    """A vendor's listings for an OEM part number (vendors/ mock counter; fallback direct catalog query)."""
    listings = None
    if _mock_up():
        try:
            import httpx
            r = httpx.get(f"{VENDOR_URL}/v/{vendor_id}/search", params={"oem": oem_part_no}, timeout=3)
            if r.status_code == 200:
                listings = r.json().get("listings")
        except Exception:
            listings = None
    source = "vendors-mock"
    if listings is None:
        from vendors.catalog import search as vsearch
        listings = vsearch(vendor_id, oem_part_no)
        source = "catalog-direct"
    return {"listings": listings, "vendor_id": vendor_id, "source": source}


# ------------------------------------------------------------------------------------------ matching
MATCH_VECTOR_SQL = (
    "SELECT vendor_id, sku, brand, description, DOT_PRODUCT(embedding, %s :> VECTOR(1024)) AS score "
    "FROM vendor_catalog WHERE oem_part_no = %s OR description LIKE %s ORDER BY score DESC LIMIT 10")


def _sigmoid(x: float) -> float:
    try:
        return 1 / (1 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _sie_scores(query: str, texts: list[str]) -> tuple[list[float] | None, str]:
    """SIE rerank (cross-encoder logits, aligned to input order) -> (scores, source)."""
    res = backends.call("sie", ("rerank",), query, texts)
    if not isinstance(res, dict) or not res.get("results"):
        return None, "none"
    out = [0.0] * len(texts)
    for r in res["results"]:
        out[int(r["index"])] = float(r["score"])
    return out, res.get("source", "live")


@safe
def match_listings(oem_part_no: str, listings: list[dict]) -> dict:
    """Same / variant / different part? SIE rerank score + OEM/fitment guard (SingleStore)."""
    target = _part_by_oem(oem_part_no) or {}
    q = f"{target.get('description') or ''} OEM {oem_part_no}".strip()
    texts = [f"{lst.get('brand', '')} {lst.get('desc') or lst.get('description') or ''}" for lst in listings]
    scores, sie_src = _sie_scores(q, texts) if listings else (None, "none")
    method = f"sie-rerank({sie_src})+fitment-guard" if scores else "oem-join"
    tpos = (target.get("position") or "").lower()
    opposite = {"downstream": "upstream", "upstream": "downstream"}.get(tpos)
    results = []
    for i, lst in enumerate(listings):
        oem = lst.get("oem_part_no")
        if not oem:
            row = _catalog_row(lst.get("vendor_id"), lst.get("sku", "")) or {}
            oem = row.get("oem_part_no")
        other = _part_by_oem(oem) if oem else None
        text = texts[i].lower()
        if opposite and opposite in text and tpos not in text:
            verdict = "different"  # cross-referenced to this OEM no. but the listing says the other position
        elif oem and oem == oem_part_no:
            verdict = "same"
        elif other and target and (other.get("part_type") != target.get("part_type")
                                   or (other.get("position") or "") != (target.get("position") or "")):
            verdict = "different"
        else:
            verdict = "variant"
        sc = round(_sigmoid(scores[i]), 3) if scores else {"same": 1.0, "variant": 0.5, "different": 0.0}[verdict]
        results.append({"sku": lst.get("sku"), "vendor_id": lst.get("vendor_id"), "verdict": verdict, "score": sc,
                        "brand": lst.get("brand"), "price": lst.get("price"), "eta_minutes": lst.get("eta_minutes")})
    vec = None
    emb = backends.call("sie", ("embed",), [q], True)
    emb = emb.get("vectors", [None])[0] if isinstance(emb, dict) and emb.get("source") != "fallback" else None
    if emb:
        vec = data.vector_search("vendor_catalog", list(emb), k=5, where="oem_part_no = %s", params=(oem_part_no,))
    out = {"results": results, "method": method, "vector_hits": vec or []}
    diff = [r for r in results if r["verdict"] == "different"]
    srcs = [{"name": "Vendor", "ref": v} for v in sorted({r["vendor_id"] for r in results if r.get("vendor_id")})]
    if scores:
        srcs.append({"name": "SIE", "ref": os.environ.get("SIE_RERANK_MODEL") or "rerank"})
    srcs.append({"name": "SingleStore", "ref": "vendor_catalog"})
    events.emit("vendors.compared",
                f"Compared {len(results)} listings for {oem_part_no}" + (f"; {len(diff)} not the same part" if diff else ""),
                sources=srcs, refs={"part_no": oem_part_no}, data={"listings": results, "method": method})
    return out


@safe
def get_brand_history(brand: str, part_type: str) -> dict:
    """The shop's own purchase/comeback history for a brand (SingleStore purchase_history)."""
    rows, backend = data.query(
        "SELECT COUNT(*) AS purchases, COALESCE(SUM(CASE WHEN comeback THEN 1 ELSE 0 END), 0) AS comebacks "
        "FROM purchase_history WHERE LOWER(brand) = LOWER(%s) AND part_type = %s", (brand, part_type),
        allow_empty_fallback=False)
    r = rows[0] if rows else {"purchases": 0, "comebacks": 0}
    p, c = int(_num(r.get("purchases"))), int(_num(r.get("comebacks")))
    if p == 0 and backend == "singlestore":
        rows, backend = data._local_query(
            "SELECT COUNT(*) AS purchases, COALESCE(SUM(comeback),0) AS comebacks FROM purchase_history "
            "WHERE LOWER(brand)=LOWER(?) AND part_type=?", (brand, part_type)), "fixtures"
        p, c = int(rows[0]["purchases"]), int(rows[0]["comebacks"])
    out = {"purchases": p, "comebacks": c, "comeback_rate": round(c / p, 3) if p else 0.0, "backend": backend}
    events.emit("context.retrieved", f"{brand} {part_type.replace('_', ' ')}: {c} comebacks in {p} purchases",
                sources=[{"name": "SingleStore", "ref": "purchase_history"}],
                data={"kind": "brand_history", "brand": brand, "part_type": part_type, **out})
    return out


# ----------------------------------------------------------------------------------------- quoting
MARKUP_MATRIX = [  # (upper bound inclusive, multiplier, rule id) — R2, seeded from the Senso "Markup matrix" doc
    (25.0, 2.5, "R2.1"), (75.0, 2.0, "R2.2"), (200.0, 1.7, "R2.3"), (float("inf"), 1.5, "R2.4")]


@safe
def compute_quote(wholesale: float) -> dict:
    """Retail price from the R2 markup matrix (deterministic)."""
    w = _num(wholesale)
    if w < 0:
        return err("bad_input", "wholesale must be >= 0")
    for upper, mult, rid in MARKUP_MATRIX:
        if w <= upper:
            return {"retail": round(w * mult, 2), "markup_pct": round((mult - 1) * 100, 1), "tier_rule_id": rid,
                    "multiplier": mult}
    raise AssertionError("unreachable")


# ------------------------------------------------------------------------------------ approvals
def _approval_file(approval_id: str) -> Path:
    return context.runs_dir() / context.run_id() / "approvals" / f"{approval_id}.json"


@safe
def request_owner_approval(ro_id: str, customer_id: str, line_items: list[dict], total: float) -> dict:
    """Send the quote to the CAR owner and get approve/decline (Firedrill Gmail; fallback UI button / auto)."""
    total = _num(total)
    approval_id = _short_id("apr", ro_id, total)
    events.emit("quote.sent", f"Quote ${total:.2f} sent to car owner for {ro_id}",
                money={"retail": total}, refs={"ro_id": ro_id, "customer_id": customer_id, "approval_id": approval_id},
                sources=[{"name": "Firedrill", "ref": "gmail"}], data={"line_items": line_items})
    events.emit("approval.requested", f"Waiting on car owner approval for {ro_id}",
                refs={"ro_id": ro_id, "approval_id": approval_id})
    res = backends.call("firedrill", ("request_approval",), ro_id, customer_id, line_items, total)
    channel, status = "firedrill-gmail", None
    if isinstance(res, dict) and res.get("status"):
        status = res["status"]
    if status is None:
        channel = "ui"
        mode = os.environ.get("SAL_CAR_OWNER_MODE", "auto")
        if mode == "wait":
            import time
            deadline = time.time() + float(os.environ.get("SAL_APPROVAL_WAIT_S", "120"))
            while time.time() < deadline and status is None:
                f = _approval_file(approval_id)
                if f.exists():
                    status = json.loads(f.read_text(encoding="utf-8")).get("status")
                    break
                time.sleep(0.5)
            status = status or "pending"
        elif mode == "pending":
            status = "pending"
        else:
            channel, status = "simulated", "approved"
    if status in ("approved", "declined"):
        events.emit("approval.received", f"Car owner {status} {ro_id} (${total:.2f})", actor="car_owner",
                    money={"retail": total}, refs={"ro_id": ro_id, "approval_id": approval_id},
                    sources=[{"name": "Firedrill" if channel.startswith("firedrill") else "Shop", "ref": channel}])
    _ledger("car_owner_approval", {"approval_id": approval_id, "ro_id": ro_id, "status": status, "total": total})
    return {"approval_id": approval_id, "status": status, "channel": channel}


@safe
def verify_owner(reason: str, order_total: float, ro_id: str | None = None) -> dict:
    """Re-verify the SHOP owner's identity (Persona inquiry) before an over-cap order. Returns inquiry_id to
    pass as approval_id to place_* tools."""
    res = backends.call("persona", ("verify_owner",), reason, _num(order_total), ro_id,
                        float(os.environ.get("SAL_OWNER_WAIT_S", "0")))
    if isinstance(res, dict) and res.get("inquiry_id"):
        if (res.get("method") == "simulated" and res.get("status") == "pending"
                and os.environ.get("SAL_OWNER_VERIFY_MODE", "auto") == "auto"):
            res = {**res, **(backends.call("persona", ("simulate_approve",), res["inquiry_id"]) or {})}
        out = {"inquiry_id": res["inquiry_id"], "status": res.get("status", "pending"),
               "verified_name": res.get("verified_name", ""), "hosted_url": res.get("hosted_url", ""),
               "method": res.get("method", "persona")}
    else:
        mode = os.environ.get("SAL_OWNER_VERIFY_MODE", "auto")
        out = {"inquiry_id": _short_id("inq_sim", reason, order_total, ro_id),
               "status": "approved" if mode == "auto" else "pending",
               "verified_name": "Shop owner (simulated)", "hosted_url": "", "method": "simulated"}
    policy.record_verification({**out, "order_total": _num(order_total), "ro_id": ro_id, "ts": context.ts()})
    events.emit("identity.verified" if out["status"] == "approved" else "approval.requested",
                f"Owner identity {out['status']} for ${_num(order_total):.2f} order ({out['method']})",
                actor="owner" if out["status"] == "approved" else "sal", reason=reason,
                sources=[{"name": "Persona", "ref": out["inquiry_id"], "url": out["hosted_url"] or None}],
                money={"wholesale": _num(order_total)},
                refs={k: v for k, v in {"ro_id": ro_id, "approval_id": out["inquiry_id"]}.items() if v})
    return out


# ------------------------------------------------------------------------------------------ orders
def _place_with_mock(vendor_id: str, sku: str, qty: int, ro_id: str | None) -> dict:
    try:
        if not _mock_up():
            raise ConnectionError("vendors mock down")
        import httpx
        r = httpx.post(f"{VENDOR_URL}/v/{vendor_id}/orders", json={"sku": sku, "qty": qty, "ro_id": ro_id,
                                                                   "run_id": context.run_id(),
                                                                   "sim_ts": context.ts()}, timeout=3)
        if r.status_code == 200:
            return {**r.json(), "channel": "vendors-mock"}
    except Exception:
        pass
    from vendors.catalog import place as vplace
    return {**vplace(vendor_id, sku, qty, ro_id, sim_ts=context.ts()), "channel": "catalog-direct"}


def _record_order(order_id, vendor_id, ro_id, total, eta, channel, external_ref, lines):
    data.execute("INSERT INTO orders (order_id, vendor_id, ro_id, placed_at, promised_at, total, channel, "
                 "external_ref, run_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                 (order_id, vendor_id, ro_id, context.now().strftime("%Y-%m-%d %H:%M:%S"),
                  str(eta)[:19].replace("T", " "), total, channel, external_ref, context.run_id()))
    for ln in lines:
        data.execute("INSERT INTO order_lines (order_id, sku, brand, part_type, qty, unit_price, core_charge) "
                     "VALUES (%s,%s,%s,%s,%s,%s,%s)", (order_id, ln.sku, ln.brand, ln.part_type, ln.qty,
                                                         ln.unit_price, 0.0))


def _part_type_for(row: dict) -> str:
    p = _part_by_oem(row.get("oem_part_no") or "") if row.get("oem_part_no") else None
    if p:
        return p["part_type"]
    inv, _ = data.query("SELECT part_type FROM inventory WHERE sku = %s", (row.get("sku"),))
    return inv[0]["part_type"] if inv else ""


@safe
def place_counter_order(vendor_id: str, sku: str, qty: int, ro_id: str, approval_id: str | None = None) -> dict:
    """Order from a local counter vendor. Policy guard applies (no-buy, spend cap w/ verified owner, routing)."""
    row = _catalog_row(vendor_id, sku)
    if not row:
        return err("unknown_sku", f"{vendor_id} has no sku {sku}")
    qty = int(qty or 1)
    price = _num(row["price"])
    total = round(price * qty, 2)
    ln = policy.Line(sku=sku, brand=row.get("brand", ""), part_type=_part_type_for(row), qty=qty, unit_price=price)
    esc = policy.guard(vendor_id, [ln], total, approval_id, ro_id)
    if esc:
        return esc
    res = _place_with_mock(vendor_id, sku, qty, ro_id)
    if "error" in res:
        return res
    out = {"order_id": res["order_id"], "eta": res["eta"], "total": _num(res.get("total"), total),
           "channel": res["channel"]}
    _record_order(out["order_id"], vendor_id, ro_id, out["total"], out["eta"], "counter", res.get("order_id"), [ln])
    v = _vendor(vendor_id)
    events.emit("order.placed", f"Ordered {qty}× {row.get('brand')} {ln.part_type.replace('_', ' ')} @ {v['name']} ${out['total']:.2f}, ETA {str(out['eta'])[11:16]}"[:140],
                money={"wholesale": out["total"]}, sources=[{"name": "Vendor", "ref": out["order_id"]}],
                refs={"order_id": out["order_id"], "vendor_id": vendor_id, "sku": sku, "ro_id": ro_id},
                data={"channel": "counter", "eta": out["eta"], "part_type": ln.part_type, "approval_id": approval_id})
    return out


@safe
def place_shopify_order(lines: list[dict], note: str = "", approval_id: str | None = None) -> dict:
    """Online restock order on the Shopify store (PartsDepot Online). lines: [{variant_id|sku, qty}].
    Fallback: mock online vendor order (labeled)."""
    resolved, plines = [], []
    for item in lines or []:
        key = item.get("variant_id") or item.get("sku") or ""
        row = _catalog_row(None, key) or _catalog_row("partsdepot", key)
        if not row:
            return err("unknown_variant", f"no catalog row for {key}")
        qty = int(item.get("qty") or 1)
        resolved.append({"variant_id": row.get("shopify_variant_id") or key, "sku": row["sku"], "qty": qty,
                         "price": _num(row["price"])})
        plines.append(policy.Line(sku=row["sku"], brand=row.get("brand", ""), part_type=_part_type_for(row),
                                  qty=qty, unit_price=_num(row["price"])))
    total = round(sum(r["price"] * r["qty"] for r in resolved), 2)
    esc = policy.guard("partsdepot", plines, total, approval_id)
    if esc:
        return esc
    shop_lines = [{"variant_id": r["variant_id"], "qty": r["qty"]} for r in resolved]
    res = backends.call("shopify", ("place_order",), shop_lines, note)
    if isinstance(res, dict) and res.get("shopify_order_id"):
        live = res.get("source") == "live"
        out = {"shopify_order_id": res["shopify_order_id"], "admin_url": res.get("admin_url", ""),
               "total": _num(res.get("total"), total), "channel": "shopify" if live else "mock-online",
               "eta": res.get("eta") or context.plus_minutes(2880)}
        src = ({"name": "Shopify", "ref": out["shopify_order_id"], "url": out["admin_url"]} if live
               else {"name": "Vendor", "ref": out["shopify_order_id"]})
    else:
        from vendors.catalog import place_many
        mock = place_many("partsdepot", [(r["sku"], r["qty"]) for r in resolved], None, sim_ts=context.ts())
        out = {"shopify_order_id": mock["order_id"], "admin_url": f"{VENDOR_URL}/v/partsdepot/orders",
               "total": mock["total"], "channel": "mock-online", "eta": mock["eta"]}
        src = {"name": "Vendor", "ref": mock["order_id"]}
    _record_order(out["shopify_order_id"], "partsdepot", None, out["total"], context.plus_minutes(2880),
                  out["channel"], out["shopify_order_id"], plines)
    n = sum(r["qty"] for r in resolved)
    events.emit("order.placed", f"Restock: {n} items on PartsDepot Online ${out['total']:.2f} ({out['channel']})",
                money={"wholesale": out["total"]}, sources=[src],
                refs={"order_id": out["shopify_order_id"], "vendor_id": "partsdepot"},
                data={"channel": out["channel"], "admin_url": out["admin_url"], "lines": resolved, "note": note,
                      "eta": out["eta"], "part_type": ",".join(sorted({ln.part_type for ln in plines if ln.part_type}))})
    return out


@safe
def record_payment(ro_id: str, customer_id: str, amount: float) -> dict:
    """Record the car owner's payment (Firedrill synthetic Stripe; fallback ledger row)."""
    res = backends.call("firedrill", ("record_payment",), ro_id, customer_id, amount)
    if isinstance(res, dict) and res.get("payment_id"):
        pid, src = res["payment_id"], {"name": "Firedrill", "ref": res["payment_id"]}
    else:
        pid = _short_id("pay", ro_id, amount)
        src = {"name": "Shop", "ref": "ledger"}
    _ledger("payment", {"payment_id": pid, "ro_id": ro_id, "customer_id": customer_id, "amount": _num(amount)})
    events.emit("payment.recorded", f"Payment ${_num(amount):.2f} recorded for {ro_id}", actor="car_owner",
                money={"retail": _num(amount)}, sources=[src], refs={"ro_id": ro_id, "payment_id": pid})
    return {"payment_id": pid}


# --------------------------------------------------------------------------------------- inventory
@safe
def get_inventory() -> dict:
    """Shop shelf inventory with min/max."""
    rows, backend = data.query("SELECT sku, name, part_type, qty, min_qty, max_qty FROM inventory ORDER BY sku")
    items = [{"sku": r["sku"], "name": r["name"], "qty": int(r["qty"]), "min_qty": int(r["min_qty"]),
              "max_qty": int(r["max_qty"]), "part_type": r.get("part_type")} for r in rows]
    low = [i for i in items if i["qty"] <= i["min_qty"]]
    events.emit("inventory.checked", f"Checked {len(items)} shelf items; {len(low)} at or below min",
                sources=[{"name": "SingleStore", "ref": "inventory"}], data={"low": [i["sku"] for i in low]})
    return {"items": items, "backend": backend}


def _bookings(days: int) -> tuple[list[dict], str]:
    start = context.now().date()
    end = start + timedelta(days=int(days))
    rows, backend = data.query(
        "SELECT booking_id, date, service_code, vehicle, parts_needed FROM bookings "
        "WHERE date >= %s AND date < %s ORDER BY date, booking_id", (start.isoformat(), end.isoformat()))
    out = []
    for r in rows:
        pn = data.parse_json(r.get("parts_needed")) or []
        out.append({"booking_id": r["booking_id"], "date": str(r["date"])[:10], "service_code": r["service_code"],
                    "vehicle": r["vehicle"], "parts_needed": pn})
    return out, backend


@safe
def get_bookings(days: int = 7) -> dict:
    """Upcoming bookings for the next N days (from the simulated 'today')."""
    rows, backend = _bookings(days)
    return {"bookings": rows, "backend": backend}


def _need_by_sku(bookings: list[dict]) -> dict[str, int]:
    need: dict[str, int] = {}
    for b in bookings:
        for p in b["parts_needed"]:
            if isinstance(p, str):
                p = {"sku": p, "qty": 1}
            need[p["sku"]] = need.get(p["sku"], 0) + int(p.get("qty", 1))
    return need


# R6 (Senso "Restock rules"): "bundle shop supplies we always use (brake cleaner, shop towels, bulbs)".
SHOP_SUPPLY_TYPES = ("brake_cleaner", "shop_towels", "bulb")


def restock_plan(inventory: list[dict], bookings: list[dict], catalog: dict[str, dict],
                 free_ship_threshold: float, bundle_window: float = 25.0) -> dict:
    """Pure R6 math: order_qty = need + min - have; if subtotal is within $window of free shipping, add the
    inventory item (with shelf room) that clears the threshold with the least overshoot."""
    need = _need_by_sku(bookings)
    inv = {i["sku"]: i for i in inventory}
    lines = []
    for sku, n in sorted(need.items()):
        i = inv.get(sku, {"qty": 0, "min_qty": 0, "max_qty": n})
        oq = max(0, n + int(i["min_qty"]) - int(i["qty"]))
        if oq > 0 and sku in catalog:
            price = _num(catalog[sku]["price"])
            lines.append({"sku": sku, "need": n, "have": int(i["qty"]), "order_qty": oq, "unit_price": price,
                          "line_total": round(price * oq, 2), "reason": "bookings"})
    subtotal = round(sum(ln["line_total"] for ln in lines), 2)
    bundle = None
    gap = round(free_ship_threshold - subtotal, 2)
    if lines and free_ship_threshold and 0 < gap <= bundle_window:
        best = None
        for sku, i in inv.items():
            if sku in {ln["sku"] for ln in lines} or sku not in catalog:
                continue
            price = _num(catalog[sku]["price"])
            if price <= 0:
                continue
            q = math.ceil(gap / price)
            if int(i["qty"]) + q > int(i["max_qty"]):
                continue
            ptype = (i.get("part_type") or "").lower()
            pref = SHOP_SUPPLY_TYPES.index(ptype) if ptype in SHOP_SUPPLY_TYPES else len(SHOP_SUPPLY_TYPES)
            key = (pref, q * price - gap)
            if best is None or key < best[0]:
                best = (key, sku, q, price, i)
        if best:
            _, sku, q, price, i = best
            bundle = {"sku": sku, "need": 0, "have": int(i["qty"]), "order_qty": q, "unit_price": price,
                      "line_total": round(q * price, 2), "reason": "R6 free-shipping bundle"}
            lines.append(bundle)
    total = round(sum(ln["line_total"] for ln in lines), 2)
    return {"lines": lines, "subtotal_before_bundle": subtotal, "total": total, "gap_to_free_ship": gap,
            "free_ship_threshold": free_ship_threshold, "bundle_added": bundle}


@safe
def plan_restock() -> dict:
    """Deterministic restock plan from next-7-day bookings + inventory, routed online with R6 bundling."""
    inv_rows, backend = data.query("SELECT sku, name, part_type, qty, min_qty, max_qty FROM inventory")
    bookings, _ = _bookings(7)
    vendor = _vendor("partsdepot")
    cat_rows, _ = data.query("SELECT * FROM vendor_catalog WHERE vendor_id = %s", ("partsdepot",))
    catalog = {r["sku"]: r for r in cat_rows}
    plan = restock_plan(inv_rows, bookings, catalog, _num(vendor.get("free_ship_threshold"), 150.0))
    for ln in plan["lines"]:
        if ln["reason"] == "bookings":
            events.emit("stock.low", f"{ln['sku']}: have {ln['have']}, need {ln['need']} for bookings",
                        sources=[{"name": "SingleStore", "ref": "inventory+bookings"}], refs={"sku": ln["sku"]},
                        data={"order_qty": ln["order_qty"]})
    for ln in plan["lines"]:
        ln["variant_id"] = catalog.get(ln["sku"], {}).get("shopify_variant_id") or ln["sku"]
    b = plan["bundle_added"]
    reason = (f"R6: ${plan['subtotal_before_bundle']:.2f} was ${plan['gap_to_free_ship']:.2f} short of free shipping "
              f"(${plan['free_ship_threshold']:.0f}); added {b['sku']} ×{b['order_qty']}" if b else
              "R6: online channel preferred for restocks")
    n = sum(ln["order_qty"] for ln in plan["lines"])
    events.emit("restock.planned", f"Restock plan: {n} items, ${plan['total']:.2f} at {vendor.get('name', 'PartsDepot Online')}",
                reason=reason, money={"wholesale": plan["total"]},
                sources=[{"name": "Senso", "ref": "R6 restock rules"}, {"name": "SingleStore", "ref": "inventory+bookings"}],
                refs={"vendor_id": "partsdepot"}, data={"lines": plan["lines"]})
    return {"lines": plan["lines"], "vendor_suggestion": {"vendor_id": "partsdepot", "name": vendor.get("name"),
                                                          "reason": reason}, "total": plan["total"],
            "subtotal_before_bundle": plan["subtotal_before_bundle"],
            "free_ship_threshold": plan["free_ship_threshold"], "bundle_added": b, "backend": backend}


# --------------------------------------------------------------------------------------- scorecard
# One SQL query (README: SingleStore section). Params: cutoff, then optional vendor/part_type filters.
SCORECARD_SQL = """
SELECT ph.vendor_id,
       COUNT(*) AS orders,
       SUM(CASE WHEN ph.delivered_at > ph.promised_at THEN 1 ELSE 0 END) AS late,
       ROUND(SUM(CASE WHEN ph.delivered_at > ph.promised_at THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 3) AS late_rate,
       SUM(CASE WHEN ph.core_credit_due > 0 AND COALESCE(ph.core_credit_received, 0) < ph.core_credit_due
                THEN 1 ELSE 0 END) AS missed_core_credits,
       SUM(CASE WHEN ph.core_credit_due > 0
                THEN ph.core_credit_due - COALESCE(ph.core_credit_received, 0) ELSE 0 END) AS missed_core_amount,
       ROUND(AVG(ph.unit_price / pt.avg_price), 3) AS avg_price_index
FROM purchase_history ph
JOIN (SELECT part_type, AVG(unit_price) AS avg_price FROM purchase_history GROUP BY part_type) pt
  ON pt.part_type = ph.part_type
WHERE ph.placed_at >= %s {filters}
GROUP BY ph.vendor_id
ORDER BY late_rate DESC
""".strip()


@safe
def get_vendor_history(vendor_id: str | None = None, part_type: str | None = None, days: int = 90) -> dict:
    """Vendor scorecard over N days (one SQL query): late rate, missed core credits, price index.
    part_type may be comma-separated, e.g. 'starter,alternator'."""
    cutoff = (context.now() - timedelta(days=int(days))).strftime("%Y-%m-%d 00:00:00")
    filters, params = "", [cutoff]
    if vendor_id:
        filters += " AND ph.vendor_id = %s"
        params.append(vendor_id)
    types = [t.strip() for t in (part_type or "").split(",") if t.strip()]
    if types:
        filters += f" AND ph.part_type IN ({','.join(['%s'] * len(types))})"
        params += types
    sql = SCORECARD_SQL.format(filters=filters)
    rows, backend = data.query(sql, params)
    per = [{"vendor_id": r["vendor_id"], "orders": int(r["orders"]), "late": int(_num(r["late"])),
            "late_rate": round(_num(r["late_rate"]), 3), "missed_core_credits": int(_num(r["missed_core_credits"])),
            "missed_core_amount": round(_num(r["missed_core_amount"]), 2),
            "avg_price_index": round(_num(r["avg_price_index"]), 3)} for r in rows]
    worst = per[0] if per else None
    summ = (f"Scorecard {days}d: {worst['vendor_id']} late {worst['late_rate'] * 100:.1f}%, "
            f"{worst['missed_core_credits']} missed core credits" if worst else "Scorecard: no orders")
    events.emit("scorecard.built", summ[:140], sources=[{"name": "SingleStore", "ref": "purchase_history"}],
                data={"per_vendor": per, "part_type": part_type, "days": days, "sql": sql})
    return {"per_vendor": per, "backend": backend, "sql": sql}


# ------------------------------------------------------------------------------------------- rules
def _evidence_sources(evidence: list) -> list[dict]:
    out = []
    for e in evidence or []:
        if isinstance(e, dict):
            name = e.get("name") or e.get("source")
            if name:
                out.append({"name": name, "ref": str(e.get("ref") or e.get("text") or e.get("fact") or "")[:120]})
        elif isinstance(e, str):
            name = next((n for n in ("SingleStore", "Cognee", "Senso", "NHTSA", "SIE") if n.lower() in e.lower()), None)
            if name:
                out.append({"name": name, "ref": e[:120]})
    return out


@safe
def propose_rule(title: str, rule_text: str, evidence: list) -> dict:
    """Propose a new shop rule to the owner (Sal can propose, never approve)."""
    rule_id = _short_id("rule", title)
    data.execute("INSERT INTO rules (rule_id, title, rule_text, status, evidence, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                 (rule_id, title, rule_text, "pending_owner", json.dumps(evidence, default=str),
                  context.now().strftime("%Y-%m-%d %H:%M:%S")))
    _ledger("rule", {"rule_id": rule_id, "title": title, "rule_text": rule_text, "evidence": evidence,
                     "status": "pending_owner"})
    events.emit("rule.proposed", f"Proposed rule: {title}"[:140], reason=rule_text[:280],
                sources=_evidence_sources(evidence), refs={"rule_id": rule_id},
                data={"title": title, "rule_text": rule_text, "evidence": evidence})
    return {"rule_id": rule_id, "status": "pending_owner"}


def _find_rule(rule_id: str) -> dict | None:
    rows, _ = data.query("SELECT * FROM rules WHERE rule_id = %s", (rule_id,))
    if rows:
        return rows[0]
    p = context.runs_dir() / context.run_id() / "ledger.jsonl"
    if p.exists():
        for line in reversed(p.read_text(encoding="utf-8").splitlines()):
            r = json.loads(line)
            if r.get("kind") == "rule" and r.get("rule_id") == rule_id:
                return r
    return None


@safe
def approve_rule(rule_id: str) -> dict:
    """OWNER/SIM ONLY (excluded from Sal). Writes the rule to Senso, remembers it in Cognee, turns on the
    Statsig routing gate."""
    rule = _find_rule(rule_id)
    if not rule:
        return err("unknown_rule", f"no rule {rule_id}")
    title, text = rule.get("title", rule_id), rule.get("rule_text", "")
    cid = backends.call("senso", ("add_doc",), title, text)
    if isinstance(cid, dict):
        cid = cid.get("content_id") or cid.get("kb_node_id")
    cid = str(cid) if cid else f"local:{rule_id}"
    backends.call("cognee", ("remember",), f"Owner approved rule: {title}. {text}", ["rule", rule_id])
    # The gate flip itself is the sim's job (sim/flags.py write_override / Statsig console); we report it.
    gate = {"name": policy.ROUTING_GATE, "on": True, "method": "sim"}
    data.execute("UPDATE rules SET status = %s, senso_content_id = %s WHERE rule_id = %s", ("approved", cid, rule_id))
    _ledger("rule_approved", {"rule_id": rule_id, "senso_content_id": cid, "gate": gate})
    events.emit("rule.approved", f"Owner approved: {title}"[:140], actor="owner", reason=text[:280],
                sources=[{"name": "Senso", "ref": cid}, {"name": "Cognee", "ref": "remember"}], refs={"rule_id": rule_id})
    events.emit("gate.enabled", f"Statsig gate {policy.ROUTING_GATE} ON", actor="system",
                sources=[{"name": "Statsig", "ref": policy.ROUTING_GATE}], refs={"rule_id": rule_id}, data=gate)
    return {"senso_content_id": cid, "statsig_gate": gate}


# ------------------------------------------------------------------------------------------ memory
def _facts_file() -> Path:
    return context.runs_dir() / "memory" / "facts.jsonl"


@safe
def remember_fact(text: str, tags: list[str] | None = None) -> dict:
    """Save something Sal OBSERVED (Cognee). Rules the owner set belong in Senso, not here."""
    res = backends.call("cognee", ("remember",), text, tags or [])
    method = "cognee" if isinstance(res, dict) and res.get("source") == "live" else "local"
    p = _facts_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"text": text, "tags": tags or [], "ts": context.ts()}) + "\n")
    events.emit("memory.saved", f"Remembered: {text}"[:140],
                sources=[{"name": "Cognee" if method == "cognee" else "Shop", "ref": method}], data={"tags": tags or []})
    return {"ok": True, "method": method}


@safe
def recall_facts(query: str) -> dict:
    """Recall facts Sal observed earlier (Cognee recall; fallback keyword search)."""
    res = backends.call("cognee", ("recall",), query)
    facts, method = None, "cognee"
    if isinstance(res, list):
        facts = [r if isinstance(r, str) else (r.get("text") or json.dumps(r, default=str)) for r in res]
    elif isinstance(res, dict) and res.get("facts"):
        facts = [f.get("text") if isinstance(f, dict) else str(f) for f in res["facts"]]
        method = "cognee" if res.get("source") == "live" else f"cognee-{res.get('source', 'fallback')}"
    elif isinstance(res, str) and res.strip():
        facts = [res]
    if not facts:
        method = "local"
        pool = list(fx.COGNEE_FACTS)
        p = _facts_file()
        if p.exists():
            pool += [json.loads(line)["text"] for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
        scored = sorted(((sum(w in f.lower() for w in words), f) for f in pool), key=lambda x: -x[0])
        facts = [f for s, f in scored if s > 0][:5]
    events.emit("context.retrieved", f"Recalled {len(facts)} facts: {query}"[:140],
                sources=[{"name": "Cognee" if method.startswith("cognee") else "Shop", "ref": f[:100]} for f in facts[:4]],
                data={"kind": "memory", "query": query, "facts": facts, "method": method})
    return {"facts": facts, "method": method}


# ----------------------------------------------------------------------------------------- intake
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_DTC_RE = re.compile(r"\b([PBCU][0-9][0-9A-F]{3})\b", re.I)
_BAY_RE = re.compile(r"\bbay\s*#?\s*(\d+)\b", re.I)
_TIME_RE = re.compile(r"\b(?:by|before|at)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)|noon)\b", re.I)
_VEH_RE = re.compile(r"\b((?:19|20)\d{2}\s+)?(Honda|Toyota|Ford|Nissan|Chevy|Chevrolet)?\s*"
                     r"(Civic|Accord|CR-V|Camry|Corolla|F-150|Altima|Silverado)\b", re.I)


def _regex_intake(text: str) -> dict:
    vin = _VIN_RE.search(text.upper())
    dtc = _DTC_RE.search(text)
    bay = _BAY_RE.search(text)
    tm = _TIME_RE.search(text)
    veh = _VEH_RE.search(text)
    return {"vin": vin.group(1) if vin else None, "dtc": dtc.group(1).upper() if dtc else None,
            "bay": int(bay.group(1)) if bay else None,
            "vehicle": " ".join(x.strip() for x in veh.groups() if x) if veh else None,
            "promise_time": tm.group(1).upper().replace(" ", " ") if tm else None, "complaint": text.strip()}


@safe
def extract_intake(text: str) -> dict:
    """Pull VIN, DTC, bay, vehicle, promise time from a tech's free-text message (SIE extract; regex guard)."""
    out = _regex_intake(text)
    labels = ["vin", "dtc code", "bay number", "vehicle", "promise time"]
    res = backends.call("sie", ("extract_entities",), text, labels)
    method = "regex"
    if isinstance(res, dict) and res.get("source") == "fallback":
        res = None
    ents = res.get("entities") if isinstance(res, dict) else res if isinstance(res, list) else None
    if ents:
        method = f"sie({res.get('model', '')})+regex"
        m = {"vin": "vin", "dtc code": "dtc", "bay number": "bay", "vehicle": "vehicle", "promise time": "promise_time"}
        for e in ents:
            k = m.get(str(e.get("label", "")).lower())
            if not k or not e.get("text"):
                continue
            v = e["text"].strip()
            if k == "vin" and not _VIN_RE.fullmatch(v.upper()):
                continue
            if k == "dtc" and not _DTC_RE.fullmatch(v):
                continue
            if k == "bay":
                d = re.search(r"\d+", v)
                if not d:
                    continue
                v = int(d.group())
            if out.get(k) is None or k in ("vehicle", "promise_time"):
                out[k] = v.upper() if k in ("vin", "dtc") else v
    out["method"] = method
    return out


# ------------------------------------------------------------------------------- statements (FRI)
STATEMENT_COLS = ["date", "invoice_no", "sku", "desc", "qty", "amount", "core_credit"]


def _csv_lines(text: str) -> list[dict]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        out.append({"date": r.get("date", ""), "invoice_no": r.get("invoice_no", ""), "sku": r.get("sku", ""),
                    "desc": r.get("desc") or r.get("description", ""), "qty": int(_num(r.get("qty"), 1)),
                    "amount": _num(r.get("amount")), "core_credit": _num(r.get("core_credit"))})
    return out


_ROW_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*\|?\s*([A-Z]{2,4}-?\d{3,}[\w-]*)\s*\|?\s*([A-Z0-9][\w-]+)\s*\|?\s*"
                     r"(.+?)\s*\|?\s*(\d+)\s*\|?\s*\$?(-?[\d,]+\.\d{2})\s*\|?\s*\$?(-?[\d,]+\.\d{2})")


def _text_rows(text: str) -> list[dict]:
    """Statement table rows out of docling/OCR text (fixed-width or markdown table)."""
    out = []
    for m in _ROW_RE.finditer(text):
        d, inv, sku, desc, qty, amt, core = m.groups()
        out.append({"date": d, "invoice_no": inv, "sku": sku, "desc": desc.strip(" |"), "qty": int(qty),
                    "amount": _num(amt.replace(",", "")), "core_credit": _num(core.replace(",", ""))})
    return out


def _ocr_text_to_lines(text: str) -> list[dict] | None:
    """Doc/OCR transcript -> lines: table regex first; CSV-ish text; else SIE small LLM structures it."""
    rows = _text_rows(text)
    if rows:
        return rows
    low = text.lower()
    if "invoice" in low and "," in text and "date" in low:
        try:
            got = _csv_lines(text[low.index("date"):])
            if got:
                return got
        except Exception:
            pass
    prompt = ("Return JSON {\"lines\": [...]} with keys " + ",".join(STATEMENT_COLS)
              + " for each statement line:\n" + text[:6000])
    res = backends.call("sie", ("llm",), [{"role": "user", "content": prompt}], {"type": "json_object"}, 2048)
    if isinstance(res, dict) and isinstance(res.get("json"), dict):
        return res["json"].get("lines") or None
    return None


@safe
def parse_vendor_statement(path: str) -> dict:
    """Parse a vendor statement (CSV; PDF via SIE doc extract; scan via SIE VLM OCR). Fallback: sibling CSV."""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        for alt in (ROOT / "seed" / "statements" / p.name, ROOT / "tools" / "samples" / p.name):
            if alt.exists():
                p = alt
                break
    if not p.exists():
        return err("not_found", f"no statement at {path}")
    ext = p.suffix.lower()
    lines, method, model = None, "csv", ""
    schema = {"type": "object", "properties": {"vendor": {"type": "string"}, "statement_date": {"type": "string"},
              "lines": {"type": "array", "items": {"type": "object", "properties": {c: {"type": "string"} for c in STATEMENT_COLS}}}}}
    instr = "Extract every statement line: date, invoice_no, sku, desc, qty, amount, core_credit (0 if none)."
    if ext == ".pdf":
        res = backends.call("sie", ("extract_document",), str(p), schema, instr)
        dd = (res.get("data") or {}) if isinstance(res, dict) and res.get("method") == "doc" else {}
        got = dd.get("lines") or (_ocr_text_to_lines(dd["text"]) if dd.get("text") else None)
        if got:
            lines, method, model = got, "doc", res.get("model", "")
    elif ext in (".png", ".jpg", ".jpeg"):
        res = backends.call("sie", ("ocr_image",), str(p))
        if isinstance(res, dict) and res.get("text"):
            model = res.get("model", "")
            lines = _ocr_text_to_lines(res["text"])
            method = "ocr" if lines else method
    if lines is None:
        csv_path = p if ext == ".csv" else p.with_name(re.sub(r"_scan$", "", p.stem) + ".csv")
        if not csv_path.exists():
            return err("unparsed", f"could not parse {p.name} and no CSV fallback")
        lines, method = _csv_lines(csv_path.read_text(encoding="utf-8")), "csv"
    lines = [{c: ln.get(c) for c in STATEMENT_COLS} for ln in lines]
    for ln in lines:
        ln["qty"], ln["amount"], ln["core_credit"] = int(_num(ln["qty"], 1)), _num(ln["amount"]), _num(ln["core_credit"])
    vendor_id = next((v["vendor_id"] for v in fx.VENDORS if v["vendor_id"] in p.name.lower()), "bayshore")
    m = re.search(r"(20\d{2}-\d{2})", p.name)
    out = {"vendor_id": vendor_id, "statement_date": (m.group(1) + "-30") if m else context.now().date().isoformat(),
           "lines": lines, "total": round(sum(ln["amount"] - ln["core_credit"] for ln in lines), 2),
           "model": model, "method": method}
    events.emit("statement.parsed", f"{_vendor(vendor_id).get('name', vendor_id)} statement: {len(lines)} lines parsed ({method})",
                sources=[{"name": "SIE" if method != "csv" else "Vendor", "ref": model or p.name}],
                refs={"vendor_id": vendor_id}, data={"method": method, "total": out["total"], "path": p.name})
    return out


@safe
def reconcile_statement(vendor_id: str, lines: list[dict]) -> dict:
    """Join statement lines against purchase_history: which core credits are owed but missing."""
    rows, backend = data.query(
        "SELECT order_id, part_type, placed_at, core_credit_due, core_credit_received FROM purchase_history "
        "WHERE vendor_id = %s AND core_credit_due > 0 ORDER BY placed_at", (vendor_id,))
    credited: dict[str, float] = {}
    for ln in lines or []:
        credited[str(ln.get("invoice_no"))] = credited.get(str(ln.get("invoice_no")), 0) + _num(ln.get("core_credit"))
    missing = []
    for r in rows:
        got = max(_num(r.get("core_credit_received")), credited.get(r["order_id"], 0.0))
        due = round(_num(r["core_credit_due"]) - got, 2)
        if due > 0:
            sku = next((ln.get("sku") for ln in lines or [] if str(ln.get("invoice_no")) == r["order_id"]), r["part_type"])
            missing.append({"order_id": r["order_id"], "sku": sku, "due": due, "placed_at": str(r["placed_at"])[:10]})
    total_due = round(sum(m["due"] for m in missing), 2)
    vname = _vendor(vendor_id).get("name", vendor_id)
    draft = (f"Hi {vname} accounts team,\n\nOur records show core returns on the following invoices were not credited:\n"
             + "".join(f"- {m['order_id']} ({m['sku']}, {m['placed_at']}): ${m['due']:.2f}\n" for m in missing)
             + f"\nTotal due: ${total_due:.2f}. Please apply the credits to our account.\n\nMission Street Auto")
    if missing:
        events.emit("escalation", f"{vname}: {len(missing)} missing core credits (${total_due:.2f}); dispute drafted, not sent",
                    reason="Statement reconciled against purchase_history; owner reviews before sending.",
                    sources=[{"name": "SingleStore", "ref": "purchase_history"}, {"name": "Vendor", "ref": "statement"}],
                    money={"saved": total_due}, refs={"vendor_id": vendor_id}, data={"missing": missing})
    return {"missing_core_credits": missing, "total_due": total_due, "dispute_draft": draft, "backend": backend}


# ------------------------------------------------------------------------------------- shop data
@safe
def search_shop_data(query: str, stream: str | None = None) -> dict:
    """Search the shop's synced sheets (Airbyte context layer: bookings, price_sheets); fallback local CSVs."""
    res = backends.call("airbyte", ("search_shop_data",), query, stream)
    if isinstance(res, dict) and res.get("records") is not None:
        recs, source = res["records"], res.get("source", "airbyte")
    elif isinstance(res, list):
        recs, source = res, "airbyte"
    else:
        source = "csv"
        recs = []
        words = [w for w in re.findall(r"[a-z0-9-]+", query.lower()) if len(w) > 2]
        folder = ROOT / "seed" / "shop_sheets"
        streams = [stream] if stream else ["bookings", "price_sheets"]
        for s in streams:
            f = folder / f"{s}.csv"
            if f.exists():
                rows = list(csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))))
            elif s == "bookings":
                rows = [{**b, "parts_needed": json.dumps(b["parts_needed"])} for b in _bookings(30)[0]]
            else:
                rows = [{k: v for k, v in r.items() if k != "embedding"}
                        for r in data.query("SELECT * FROM vendor_catalog")[0]]
            for i, r in enumerate(rows):
                blob = " ".join(str(v) for v in r.values()).lower()
                if not words or any(w in blob for w in words):
                    recs.append({"stream": s, "id": str(r.get("booking_id") or r.get("sku") or i),
                                 "fields": {k: v for k, v in r.items()}})
        recs = recs[:20]
    events.emit("context.retrieved", f"Shop data search '{query}': {len(recs)} records ({source})"[:140],
                sources=[{"name": "Airbyte" if source == "airbyte" else "Shop", "ref": stream or "all"}],
                data={"kind": "shop_data", "query": query, "count": len(recs)})
    return {"records": recs, "source": source}


@safe
def emit_event(event: dict) -> dict:
    """Log a SalEvent (partial ok: type + summary minimum). Use for part.rejected, part.chosen, sal.summary."""
    evt = events.emit_raw(event)
    if evt.get("type") == "error" and (event or {}).get("type") != "error":
        return err("invalid_event", evt.get("reason", "event failed schema validation"))
    return {"id": evt.get("id", "")}
