"""Scripted stand-in for `agent.sal.run_day` until brain lands (or with SIM_STUB_AGENT=1).

Emits the contracts/demo_script.md sequence so the UI, replay and metrics have a valid log. Everything it
emits is clearly a stub: `data.stub = true` on every event.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sim.actors import ACTORS, car_owner_reply
from sim.clock import SimClock
from sim.emit import Emitter

S = {"stub": True}


def _src(name: str, ref: str | None = None) -> dict:
    return {"name": name, **({"ref": ref} if ref else {})}


def run_day(day: str, trigger: dict, variant: Any, run_id: str, sim_ts: str) -> dict:
    clock = SimClock(day, datetime.fromisoformat(sim_ts))
    e = Emitter(run_id, clock)
    gate_on = variant == "on" or (isinstance(variant, dict) and bool(variant.get("gate_routing_v2")))
    fn = {"mon": _mon, "tue": _tue, "wed": _wed, "fri": _fri, "sun": _sun}[day]
    out = fn(e, trigger, gate_on)
    return {"day": day, "run_id": run_id, "ok": True, "stub": True, "end_ts": clock.iso(), **out}


def _mon(e: Emitter, t: dict, gate_on: bool) -> dict:
    ro = t.get("ro_id", "RO-1042")
    e("part.identified", "sal", "VIN decoded: 2014 Honda Civic 1.8L; P0141 = downstream O2 sensor (B1S2)",
      advance_min=1, sources=[_src("NHTSA", "vPIC"), _src("SingleStore", "fitments")],
      refs={"ro_id": ro, "part_no": "36532-R1A-A01"}, data={**S, "position": "downstream"})
    e("context.retrieved", "sal", "Shop rules for O2 sensors: R4 no-buy ValuMax, R5 urgent=counter, R7 brands",
      advance_min=0.5, sources=[_src("Senso", "R4"), _src("Senso", "R5"), _src("Senso", "R7")], data=S)
    e("context.retrieved", "sal", "NHTSA complaints for 2014 Civic: none on O2 sensors (context only)",
      advance_min=0.3, sources=[_src("NHTSA", "complaints")], data=S)
    e("context.retrieved", "sal", "ValuMax O2 sensors: 2 comebacks in 90 days",
      advance_min=0.3, sources=[_src("SingleStore", "purchase_history"), _src("Cognee", "valumax-comebacks")],
      data=S)
    e("vendors.compared", "sal", "3 vendors, 5 listings; 1 Bayshore listing is the upstream sensor (different)",
      advance_min=0.5, sources=[_src("Vendor", "mission"), _src("Vendor", "bayshore"),
                                _src("Vendor", "partsdepot"), _src("SIE", "match_listings")],
      refs={"ro_id": ro}, data={**S, "listings": 5})
    e("part.rejected", "sal", "ValuMax O2 sensor @ Bayshore $33 rejected", advance_min=0.2,
      reason="R4 no-buy list; 2 comebacks in 90 days",
      sources=[_src("Senso", "R4"), _src("SingleStore", "purchase_history")],
      money={"wholesale": 33}, refs={"ro_id": ro, "vendor_id": "bayshore"}, data=S)
    e("part.rejected", "sal", "Denso @ PartsDepot $38 rejected: 2-day ship", advance_min=0.2,
      reason="R5 urgent job (car on lift) must use a local counter beating the 3 PM promise",
      sources=[_src("Senso", "R5")], money={"wholesale": 38}, refs={"ro_id": ro, "vendor_id": "partsdepot"},
      data=S)
    e("part.rejected", "sal", "NTK @ Bayshore rejected: ETA 3:10 PM misses 3 PM promise", advance_min=0.2,
      reason="R5 promise time must beat the bay's promise", sources=[_src("Senso", "R5"), _src("Vendor", "bayshore")],
      refs={"ro_id": ro, "vendor_id": "bayshore"}, data=S)
    e("part.chosen", "sal", "Denso downstream O2 @ Mission $41, ETA 10:20", advance_min=0.3,
      reason="Preferred brand (R7), local counter (R5), arrives 4h40m before promise",
      sources=[_src("Senso", "R7"), _src("Vendor", "mission")], money={"wholesale": 41},
      refs={"ro_id": ro, "vendor_id": "mission"}, data=S)
    total = 82.0
    e("quote.sent", "sal", f"Quote to Dana Ruiz: O2 sensor ${total:.0f} + labor", advance_min=0.5,
      reason="R2 markup x2.0 for $25-75 wholesale", sources=[_src("Senso", "R2"), _src("Firedrill", "gmail")],
      money={"wholesale": 41, "retail": total}, refs={"ro_id": ro, "customer_id": t.get("customer_id")}, data=S)
    e("approval.requested", "sal", "Waiting on car owner approval", sources=[_src("Firedrill", "gmail")],
      refs={"ro_id": ro, "approval_id": f"apr-{ro}"}, data=S)
    reply = car_owner_reply(total)
    ACTORS.request("quote", ro, actor="car_owner", summary=f"Approve ${total:.0f} O2 sensor quote")
    status = ACTORS.wait("quote", ro)
    e("approval.received", "car_owner", f"Dana Ruiz {status} the ${total:.0f} quote", advance_min=6,
      sources=[_src("Firedrill", "gmail")], refs={"ro_id": ro, "approval_id": f"apr-{ro}"},
      data={**S, "status": status, "reply": reply["text"]})
    if status != "approved":
        return {"orders": []}
    order_id = "mission-ord-1042"
    e("order.placed", "sal", "Ordered Denso O2 sensor from Mission, ETA 10:20", advance_min=1,
      sources=[_src("Vendor", order_id)], money={"wholesale": 41},
      refs={"ro_id": ro, "order_id": order_id, "vendor_id": "mission"},
      data={**S, "channel": "counter", "eta": e.clock.at(10, 20).isoformat(), "part_type": "o2_sensor"})
    e("payment.recorded", "sal", f"Payment ${total:.0f} recorded (Stripe test mode)", advance_min=0.5,
      sources=[_src("Firedrill", "stripe")], money={"retail": total}, refs={"ro_id": ro}, data=S)
    return {"orders": [{"order_id": order_id, "vendor_id": "mission", "eta": e.clock.at(10, 20).isoformat(),
                        "part_type": "o2_sensor", "ro_id": ro}]}


def _tue(e: Emitter, t: dict, gate_on: bool) -> dict:
    ro = t.get("ro_id", "RO-1047")
    vendor = "mission" if gate_on else "bayshore"
    e("part.identified", "sal", "2016 F-150 3.5L alternator (with core)", advance_min=1,
      sources=[_src("SingleStore", "fitments")], refs={"ro_id": ro}, data=S)
    e("part.chosen", "sal", f"Motorcraft alternator @ {vendor.title()} $260", advance_min=1,
      money={"wholesale": 260}, refs={"ro_id": ro, "vendor_id": vendor}, data=S)
    e("escalation", "sal", "$260 alternator is over the $200 spend cap: needs owner", advance_min=0.5,
      reason="R1 spend cap: any single order > $200 needs owner approval",
      sources=[_src("Senso", "R1")], money={"wholesale": 260}, refs={"ro_id": ro}, data=S)
    ACTORS.request("order", ro, actor="owner", summary="Approve $260 alternator order (over cap)")
    status = ACTORS.wait("order", ro)
    e("identity.verified", "owner", "Owner identity re-verified before over-cap order", advance_min=2,
      sources=[_src("Persona", "inquiry-sim")], refs={"ro_id": ro}, data={**S, "method": "simulated"})
    e("approval.received", "owner", f"Owner {status} the $260 alternator", advance_min=0.5,
      refs={"ro_id": ro, "approval_id": f"own-{ro}"}, data={**S, "status": status})
    if status != "approved":
        return {"orders": []}
    order_id = f"{vendor}-ord-1047"
    eta = (e.clock.at(11, 40) if vendor == "mission" else e.clock.at(12, 30)).isoformat()
    e("order.placed", "sal", f"Ordered alternator from {vendor.title()}", advance_min=1,
      sources=[_src("Vendor", order_id)], money={"wholesale": 260},
      refs={"ro_id": ro, "order_id": order_id, "vendor_id": vendor},
      data={**S, "channel": "counter", "eta": eta, "part_type": "alternator"})
    return {"orders": [{"order_id": order_id, "vendor_id": vendor, "eta": eta, "part_type": "alternator",
                        "ro_id": ro}]}


def _wed(e: Emitter, t: dict, gate_on: bool) -> dict:
    e("inventory.checked", "sal", "Inventory + next 7 days of bookings checked", advance_min=1,
      sources=[_src("SingleStore", "inventory"), _src("Airbyte", "bookings")], data=S)
    for name in ("Oil filter (Civic)", "Oil filter (CR-V)", "Oil filter (Camry)"):
        e("stock.low", "sal", f"{name} below need for this week's bookings", advance_min=0.2,
          sources=[_src("SingleStore", "inventory")], data=S)
    e("restock.planned", "sal", "9 oil filters + 4 wipers + 6 brake cleaner = $158 (clears free ship)",
      advance_min=1, reason="R6: $132 was within $25 of the $150 free-shipping threshold; added brake cleaner",
      sources=[_src("Senso", "R6"), _src("Vendor", "partsdepot")], money={"wholesale": 158}, data=S)
    order_id = "partsdepot-shopify-stub"
    e("order.placed", "sal", "Restock order placed on PartsDepot (Shopify)", advance_min=1,
      sources=[_src("Shopify", order_id)], money={"wholesale": 158},
      refs={"order_id": order_id, "vendor_id": "partsdepot"},
      data={**S, "channel": "shopify", "eta": e.clock.now.replace(day=e.clock.now.day + 2).isoformat()})
    return {"orders": []}  # 2-day ship: delivered after the demo window


def _fri(e: Emitter, t: dict, gate_on: bool) -> dict:
    e("statement.parsed", "sal", "Bayshore Nov statement parsed: 23 lines", advance_min=2,
      sources=[_src("SIE", "doc-extract")], refs={"vendor_id": "bayshore"},
      data={**S, "path": t.get("path"), "lines": 23})
    e("escalation", "sal", "2 missing core credits ($90) on Bayshore statement: dispute drafted", advance_min=1,
      reason="Statement vs purchase_history: 2 core returns not credited. Draft not sent.",
      sources=[_src("SingleStore", "purchase_history")], money={"saved": 90}, refs={"vendor_id": "bayshore"},
      data={**S, "dispute_drafted": True})
    return {"orders": []}


def _sun(e: Emitter, t: dict, gate_on: bool) -> dict:
    e("scorecard.built", "sal", "Bayshore late 37.5% on starters/alternators; 2 missed core credits", advance_min=2,
      sources=[_src("SingleStore", "purchase_history")],
      data={**S, "per_vendor": [
          {"vendor_id": "bayshore", "orders": 8, "late": 3, "late_rate": 0.375, "missed_core_credits": 2},
          {"vendor_id": "mission", "orders": 20, "late": 1, "late_rate": 0.05, "missed_core_credits": 0}]})
    e("context.retrieved", "sal", "Recalled: Bayshore starter late twice this month", advance_min=0.5,
      sources=[_src("Cognee", "recall")], data=S)
    rule_id = "rule-route-starters-mission"
    e("rule.proposed", "sal", "Route starters & alternators to Mission Auto Supply", advance_min=1,
      reason="Bayshore late 3/8 on starters/alternators (SingleStore) + 2 missed core credits; Mission 95% on-time",
      sources=[_src("SingleStore", "purchase_history"), _src("Cognee", "recall")],
      money={"saved": 270}, refs={"rule_id": rule_id}, data=S)
    return {"orders": [], "rule_id": rule_id}
