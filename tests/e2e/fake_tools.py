"""Minimal canned sal-tools server for exercising agent/sal.py before/independently of tools/server.py.

Implements the contracts/tools.md shapes for the MON flow (plus emit_event). Events go to
runs/<SAL_RUN_ID>/events.jsonl. Run: SAL_TOOLS_MODULE=tests.e2e.fake_tools python -m agent.sal --day mon
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from mcp.server.mcpserver import MCPServer

ROOT = Path(__file__).resolve().parents[2]
mcp = MCPServer("sal-tools")


def _emit(**ev) -> dict:
    run_id = os.getenv("SAL_RUN_ID", "fake")
    full = {"id": "evt_" + uuid.uuid4().hex[:12], "run_id": run_id, "ts": os.getenv("SAL_SIM_TS", "2026-11-16T09:12:00-08:00"),
            "day": os.getenv("SAL_DAY", "mon"), "actor": "sal", **ev}
    full["summary"] = str(full.get("summary", ""))[:140]
    if "reason" in full:
        full["reason"] = str(full["reason"])[:280]
    p = ROOT / "runs" / run_id / "events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(full) + "\n")
    return full


@mcp.tool()
def extract_intake(text: str) -> dict:
    return {"vin": "19XFB2F58EE200123", "dtc": "P0141", "bay": 2, "vehicle": "2014 Honda Civic",
            "promise_time": "2026-11-16T15:00:00-08:00", "complaint": text}


@mcp.tool()
def decode_vin(vin: str) -> dict:
    _emit(type="part.identified", summary="VIN decoded: 2014 Honda Civic 1.8L", sources=[{"name": "NHTSA", "ref": "vpic"}])
    return {"year": 2014, "make": "Honda", "model": "Civic", "trim": "LX", "engine_l": 1.8, "cylinders": 4,
            "raw_source_url": "https://vpic.nhtsa.dot.gov/"}


@mcp.tool()
def identify_part(year: int, make: str, model: str, engine_l: float, dtc: str = "", symptom: str = "") -> dict:
    _emit(type="part.identified", summary="P0141 -> downstream O2 sensor 36532-R1A-A01",
          sources=[{"name": "SingleStore", "ref": "fitments"}], refs={"part_no": "36532-R1A-A01"})
    return {"oem_part_no": "36532-R1A-A01", "part_type": "o2_sensor", "position": "bank 1 sensor 2 (downstream)",
            "notes": "P0141 = downstream heater circuit", "candidates": ["36532-R1A-A01"]}


@mcp.tool()
def get_shop_rules(question: str) -> dict:
    _emit(type="context.retrieved", summary="Shop rules: R4, R5, R7", sources=[{"name": "Senso", "ref": "R4"}])
    return {"answer": "Urgent: local counter only, ETA must beat promise (R5). ValuMax no-buy for sensors (R4). "
                      "Preferred O2: Denso, NTK, Bosch (R7).",
            "passages": [{"content_id": "R4", "title": "No-buy", "chunk_text": "ValuMax sensors"},
                         {"content_id": "R5", "title": "Urgent", "chunk_text": "local counter"},
                         {"content_id": "R7", "title": "O2 brands", "chunk_text": "Denso NTK Bosch"}]}


@mcp.tool()
def get_complaints(make: str, model: str, year: int, component_keyword: str) -> dict:
    _emit(type="context.retrieved", summary="NHTSA complaints: 3 match", sources=[{"name": "NHTSA", "ref": "complaints"}])
    return {"total": 41, "matching": 3, "top": [], "source_url": "https://api.nhtsa.gov/complaints"}


@mcp.tool()
def get_brand_history(brand: str, part_type: str) -> dict:
    bad = brand.lower() == "valumax"
    _emit(type="context.retrieved", summary=f"{brand} history", sources=[{"name": "SingleStore", "ref": "purchase_history"}])
    return {"purchases": 6 if bad else 12, "comebacks": 2 if bad else 0, "comeback_rate": 0.33 if bad else 0.0}


@mcp.tool()
def recall_facts(query: str) -> dict:
    _emit(type="context.retrieved", summary="Cognee facts", sources=[{"name": "Cognee", "ref": "recall"}])
    return {"facts": ["Bayshore was late on 3 of 8 starter orders."]}


LISTINGS = {
    "mission": [{"vendor_id": "mission", "sku": "MS-DEN-234-4210", "vendor_part_no": "234-4210", "brand": "Denso",
                 "desc": "O2 sensor downstream", "price": 41.0, "qty_on_hand": 2, "eta_minutes": 68, "core_charge": 0}],
    "bayshore": [{"vendor_id": "bayshore", "sku": "BS-VMX-O2-77", "vendor_part_no": "VMX-O2-77", "brand": "ValuMax",
                  "desc": "O2 sensor downstream", "price": 33.0, "qty_on_hand": 5, "eta_minutes": 45, "core_charge": 0},
                 {"vendor_id": "bayshore", "sku": "BS-NTK-24100", "vendor_part_no": "24100", "brand": "NTK",
                  "desc": "O2 sensor upstream A/F", "price": 52.0, "qty_on_hand": 1, "eta_minutes": 358, "core_charge": 0}],
    "partsdepot": [{"vendor_id": "partsdepot", "sku": "PD-DEN-234-4210", "vendor_part_no": "234-4210", "brand": "Denso",
                    "desc": "O2 sensor downstream", "price": 38.0, "qty_on_hand": 9, "eta_minutes": 2880, "core_charge": 0}],
}


@mcp.tool()
def search_vendor(vendor_id: str, oem_part_no: str) -> dict:
    return {"listings": LISTINGS.get(vendor_id, [])}


@mcp.tool()
def match_listings(oem_part_no: str, listings: list[dict]) -> dict:
    out = [{"sku": x.get("sku"), "verdict": "different" if "upstream" in str(x.get("desc", "")) else "same",
            "score": 0.31 if "upstream" in str(x.get("desc", "")) else 0.94} for x in listings]
    _emit(type="vendors.compared", summary=f"{len(listings)} listings compared", sources=[{"name": "SIE", "ref": "match"}])
    return {"results": out}


@mcp.tool()
def compute_quote(wholesale: float) -> dict:
    mult = 2.5 if wholesale <= 25 else 2.0 if wholesale <= 75 else 1.7 if wholesale <= 200 else 1.5
    return {"retail": round(wholesale * mult, 2), "markup_pct": round((mult - 1) * 100), "tier_rule_id": "R2"}


@mcp.tool()
def request_owner_approval(ro_id: str, customer_id: str, line_items: list[dict], total: float) -> dict:
    for t in ("quote.sent", "approval.requested"):
        _emit(type=t, summary=f"{t} {ro_id} ${total}", sources=[{"name": "Firedrill", "ref": "gmail"}])
    _emit(type="approval.received", actor="car_owner", summary=f"Approved {ro_id}", sources=[{"name": "Firedrill"}])
    return {"approval_id": "APR-1", "status": "approved", "channel": "firedrill_gmail"}


@mcp.tool()
def verify_owner(reason: str, order_total: float, ro_id: str = "") -> dict:
    _emit(type="identity.verified", actor="owner", summary="Owner verified", sources=[{"name": "Persona", "ref": "inq_1"}])
    return {"inquiry_id": "inq_1", "status": "approved", "verified_name": "Owner", "hosted_url": "", "method": "simulated"}


@mcp.tool()
def place_counter_order(vendor_id: str, sku: str, qty: int, ro_id: str) -> dict:
    if "VMX" in sku:
        _emit(type="escalation", summary="Blocked: ValuMax no-buy", sources=[{"name": "Senso", "ref": "R4"}])
        return {"escalation": {"rule_id": "R4", "message": "ValuMax is on the no-buy list"}}
    price = next((x["price"] for v in LISTINGS.values() for x in v if x["sku"] == sku), 0.0)
    _emit(type="order.placed", summary=f"Ordered {sku} from {vendor_id}", money={"wholesale": price, "currency": "USD"},
          refs={"order_id": "ORD-1", "sku": sku, "vendor_id": vendor_id, "ro_id": ro_id}, sources=[{"name": "Vendor", "ref": vendor_id}])
    return {"order_id": "ORD-1", "eta": "2026-11-16T10:20:00-08:00", "total": price * qty}


@mcp.tool()
def record_payment(ro_id: str, customer_id: str, amount: float) -> dict:
    _emit(type="payment.recorded", summary=f"Payment ${amount} for {ro_id}", sources=[{"name": "Firedrill", "ref": "stripe"}])
    return {"payment_id": "PAY-1"}


@mcp.tool()
def remember_fact(text: str, tags: list[str]) -> dict:
    _emit(type="memory.saved", summary=text[:140], sources=[{"name": "Cognee"}])
    return {"ok": True}


@mcp.tool()
def emit_event(type: str, summary: str, actor: str = "sal", reason: str = "", sources: list[dict] | None = None,
               money: dict | None = None, refs: dict | None = None, data: dict | None = None) -> dict:
    ev = {"type": type, "summary": summary, "actor": actor}
    for k, v in (("reason", reason), ("sources", sources), ("money", money), ("refs", refs), ("data", data)):
        if v:
            ev[k] = v
    return {"id": _emit(**ev)["id"]}


@mcp.tool()
def approve_rule(rule_id: str) -> dict:
    return {"error": {"code": "forbidden", "message": "Sal must never call this"}}


if __name__ == "__main__":
    mcp.run()
