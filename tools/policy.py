"""Policy guard applied inside every place_* tool (contracts/tools.md, contracts/policy.md R1/R4 + routing gate).

`check_order(...)` returns None (allowed) or an escalation dict. `guard(...)` additionally emits the
`escalation` event and returns {"escalation": {...}} ready to hand back to Sal.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from tools import context, events

ROUTING_GATE = "sal_vendor_routing_v2"


@dataclass
class Line:
    sku: str
    brand: str = ""
    part_type: str = ""
    qty: int = 1
    unit_price: float = 0.0


@dataclass
class Policy:
    spend_cap: float = 200.0
    # brand (lowercase) -> part_type substrings it is banned for ("*" = everything)
    no_buy: dict[str, list[str]] = field(default_factory=lambda: {"valumax": ["sensor"]})
    routing_on: bool = False
    routed_types: tuple[str, ...] = ("starter", "alternator")
    routed_vendor: str = "mission"


def _gate_on() -> bool:
    """Variant from sim (env SAL_VARIANT / context) wins; live Statsig only if SAL_GATE_SOURCE=statsig."""
    if os.environ.get("SAL_GATE_SOURCE", "env") != "statsig":
        return context.variant() in ("on", "true", "1", "routing_v2", ROUTING_GATE)
    try:  # optional live check (sim normally passes the variant via env)
        from tools.integrations import statsig_client  # type: ignore
        for fn in ("check_gate", "gate", "is_on"):
            if hasattr(statsig_client, fn):
                return bool(getattr(statsig_client, fn)(ROUTING_GATE))
    except Exception:
        pass
    return False


def _parse_no_buy(raw: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        brand, _, types = item.partition(":")
        out[brand.strip().lower()] = [t.strip().lower() for t in (types or "*").split("|") if t.strip()]
    return out


def current() -> Policy:
    p = Policy(spend_cap=float(os.environ.get("SPEND_CAP") or 200), routing_on=_gate_on())
    if os.environ.get("SAL_NO_BUY"):
        p.no_buy = _parse_no_buy(os.environ["SAL_NO_BUY"])
    if os.environ.get("SAL_ROUTED_TYPES"):
        p.routed_types = tuple(t.strip() for t in os.environ["SAL_ROUTED_TYPES"].split(",") if t.strip())
    if os.environ.get("SAL_ROUTED_VENDOR"):
        p.routed_vendor = os.environ["SAL_ROUTED_VENDOR"]
    return p


# --- owner verification ledger (verify_owner writes, guard reads) -----------------------------------
def _ledger_path():
    return context.runs_dir() / context.run_id() / "owner_verifications.jsonl"


def record_verification(rec: dict) -> None:
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def verification(approval_id: str | None) -> dict | None:
    if not approval_id:
        return None
    p = _ledger_path()
    if not p.exists():
        return None
    found = None
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("inquiry_id") == approval_id or r.get("approval_id") == approval_id:
            found = r  # last write wins (pending -> approved)
    return found


def owner_approved(approval_id: str | None) -> bool:
    r = verification(approval_id)
    return bool(r and r.get("status") == "approved")


# --- the guard --------------------------------------------------------------------------------------
def check_order(vendor_id: str, lines: list[Line], total: float, approval_id: str | None = None,
                policy: Policy | None = None) -> dict | None:
    p = policy or current()
    for ln in lines:
        banned = p.no_buy.get((ln.brand or "").lower())
        if banned and ("*" in banned or any(b in (ln.part_type or "").lower() for b in banned)):
            return {"rule": "R4", "code": "no_buy", "vendor_id": vendor_id, "sku": ln.sku, "brand": ln.brand,
                    "message": f"{ln.brand} is on the no-buy list for {ln.part_type} (R4)",
                    "needs": "pick a different brand"}
    if p.routing_on:
        for ln in lines:
            if ln.part_type in p.routed_types and vendor_id != p.routed_vendor:
                return {"rule": ROUTING_GATE, "code": "routing_gate", "vendor_id": vendor_id, "sku": ln.sku,
                        "message": f"{ln.part_type} must go to {p.routed_vendor} while {ROUTING_GATE} is ON",
                        "needs": f"order from {p.routed_vendor}"}
    if total > p.spend_cap and not owner_approved(approval_id):
        why = "no approval_id attached" if not approval_id else "approval_id is not an identity-verified owner approval"
        return {"rule": "R1", "code": "spend_cap", "vendor_id": vendor_id, "total": round(total, 2),
                "spend_cap": p.spend_cap, "approval_id": approval_id,
                "message": f"${total:.2f} exceeds the ${p.spend_cap:.0f} spend cap; {why} (R1)",
                "needs": "call verify_owner, then retry with approval_id=<inquiry_id>"}
    return None


_SOURCES = {"R4": [{"name": "Senso", "ref": "R4 no-buy list"}],
            "R1": [{"name": "Senso", "ref": "R1 spend cap"}, {"name": "Persona", "ref": "verify_owner"}],
            ROUTING_GATE: [{"name": "Statsig", "ref": ROUTING_GATE}]}


def guard(vendor_id: str, lines: list[Line], total: float, approval_id: str | None = None,
          ro_id: str | None = None) -> dict | None:
    """None if allowed, else {"escalation": {...}} after emitting the escalation event."""
    esc = check_order(vendor_id, lines, total, approval_id)
    if esc is None:
        return None
    esc["ro_id"] = ro_id
    events.emit("escalation", f"Needs owner: {esc['message']}"[:140], reason=esc["message"],
                sources=_SOURCES.get(esc["rule"], []), money={"wholesale": total},
                refs={k: v for k, v in {"ro_id": ro_id, "vendor_id": vendor_id, "sku": esc.get("sku")}.items() if v},
                data={"rule": esc["rule"], "code": esc["code"], "needs": esc["needs"]})
    return {"escalation": esc}
