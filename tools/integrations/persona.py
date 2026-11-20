"""Persona (Know Your Agent, D-006): re-verify the shop owner before an over-cap order.

API (docs.withpersona.com): base https://api.withpersona.com/api/v1, `Authorization: Bearer <key>`,
`Persona-Version: 2023-01-05`. Create: POST /inquiries {"data":{"attributes":{"inquiry-template-id","reference-id","note"}}}.
Status: GET /inquiries/{id} → data.attributes.status (created|pending|completed|approved|declined|failed|expired|needs_review).
Hosted flow: https://inquiry.withpersona.com/verify?inquiry-id=<id>. Approve (owner/sandbox): POST /inquiries/{id}/approve.
Fallback: simulated inquiry stored in runs/cache/persona/sim_<id>.json, approved by the UI button (simulate_approve).
"""

from __future__ import annotations

import json
import time
import uuid

import httpx

from ._common import cache_dir, cache_put, env, has, log, safe_exc

SERVICE = "persona"
BASE = "https://api.withpersona.com/api/v1"
HOSTED = "https://inquiry.withpersona.com/verify?inquiry-id="
APPROVED = {"approved", "completed"}
DECLINED = {"declined", "failed", "expired"}


def available() -> bool:
    return has("PERSONA_API_KEY", "PERSONA_TEMPLATE_ID")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {env('PERSONA_API_KEY')}",
        "Persona-Version": env("PERSONA_VERSION", "2023-01-05"),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _owner_name() -> str:
    return env("PERSONA_OWNER_NAME", "Shop owner (Mission Street Auto)")


def _map_status(s: str | None) -> str:
    s = (s or "").lower()
    if s in APPROVED:
        return "approved"
    if s in DECLINED:
        return "declined"
    return "pending"


def _shape(data: dict, method: str = "persona") -> dict:
    attrs = data.get("attributes") or {}
    first, last = attrs.get("name-first") or "", attrs.get("name-last") or ""
    name = (f"{first} {last}").strip() or _owner_name()
    iid = data.get("id")
    return {
        "inquiry_id": iid,
        "status": _map_status(attrs.get("status")),
        "raw_status": attrs.get("status"),
        "verified_name": name,
        "hosted_url": f"{HOSTED}{iid}",
        "method": method,
    }


# ---------------------------------------------------------------- simulated
def _sim_path(iid: str):
    return cache_dir(SERVICE) / f"sim_{iid}.json"


def _sim_create(reason: str, amount: float, ro_id: str | None) -> dict:
    iid = f"inq_sim_{uuid.uuid4().hex[:12]}"
    rec = {
        "inquiry_id": iid,
        "status": "pending",
        "verified_name": _owner_name(),
        "hosted_url": f"/verify/{iid}",
        "method": "simulated",
        "reason": reason,
        "amount": amount,
        "ro_id": ro_id,
    }
    _sim_path(iid).write_text(json.dumps(rec), encoding="utf-8")
    return rec


def simulate_approve(inquiry_id: str, approve: bool = True) -> dict:
    p = _sim_path(inquiry_id)
    try:
        rec = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {
            "inquiry_id": inquiry_id, "verified_name": _owner_name(), "hosted_url": f"/verify/{inquiry_id}", "method": "simulated",
        }
        rec["status"] = "approved" if approve else "declined"
        p.write_text(json.dumps(rec), encoding="utf-8")
        return rec
    except Exception as e:
        return {"error": {"code": "sim_failed", "message": safe_exc(e)}}


# ---------------------------------------------------------------- live
def create_inquiry(reason: str, amount: float, ro_id: str | None = None) -> dict:
    if not available():
        return _sim_create(reason, amount, ro_id)
    try:
        body = {
            "data": {
                "attributes": {
                    "inquiry-template-id": env("PERSONA_TEMPLATE_ID"),
                    "reference-id": env("PERSONA_REFERENCE_ID", "shop-001-owner"),
                    "note": f"Sal: {reason} (${amount:.2f}{', ' + ro_id if ro_id else ''})"[:250],
                }
            }
        }
        r = httpx.post(f"{BASE}/inquiries", headers=_headers(), json=body, timeout=30)
        if r.status_code >= 400:
            log(f"[persona] create http_{r.status_code}; using simulated")
            out = _sim_create(reason, amount, ro_id)
            out["warning"] = f"persona http_{r.status_code}"
            return out
        out = _shape(r.json().get("data") or {})
        cache_put(SERVICE, f"inq_{out['inquiry_id']}", out)
        return out
    except Exception as e:
        out = _sim_create(reason, amount, ro_id)
        out["warning"] = safe_exc(e)[:120]
        return out


def get_status(inquiry_id: str) -> dict:
    if inquiry_id.startswith("inq_sim_") or not available():
        p = _sim_path(inquiry_id)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {"error": {"code": "not_found", "message": inquiry_id}}
    try:
        r = httpx.get(f"{BASE}/inquiries/{inquiry_id}", headers=_headers(), timeout=30)
        if r.status_code >= 400:
            return {"error": {"code": f"http_{r.status_code}", "message": r.text[:200]}}
        return _shape(r.json().get("data") or {})
    except Exception as e:
        return {"error": {"code": "live_failed", "message": safe_exc(e)}}


def approve(inquiry_id: str) -> dict:
    """Owner/sandbox approval. Live: POST /inquiries/{id}/approve. Simulated: flips the local record."""
    if inquiry_id.startswith("inq_sim_") or not available():
        return simulate_approve(inquiry_id)
    try:
        r = httpx.post(f"{BASE}/inquiries/{inquiry_id}/approve", headers=_headers(), json={}, timeout=30)
        if r.status_code >= 400:
            return {"error": {"code": f"http_{r.status_code}", "message": r.text[:200]}}
        return _shape(r.json().get("data") or {})
    except Exception as e:
        return {"error": {"code": "live_failed", "message": safe_exc(e)}}


def verify_owner(reason: str, amount: float, ro_id: str | None = None, wait_s: float = 0) -> dict:
    """Create an inquiry for the owner; optionally poll up to wait_s for a terminal status."""
    out = create_inquiry(reason, amount, ro_id)
    iid = out.get("inquiry_id")
    deadline = time.time() + max(0.0, wait_s)
    while iid and out.get("status") == "pending" and time.time() < deadline:
        time.sleep(2)
        st = get_status(iid)
        if "error" not in st:
            out = {**out, **st}
    return out
