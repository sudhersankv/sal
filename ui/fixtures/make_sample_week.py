"""Generates ui/fixtures/sample_week.jsonl (hand-authored demo week, SPEC §10 + D-003/D-006).

Run: uv run python ui/fixtures/make_sample_week.py
The jsonl is committed; this script just keeps ids/timestamps consistent.
"""
from __future__ import annotations

import json
from pathlib import Path

RUN = "fixture"
DATES = {"mon": "2026-11-16", "tue": "2026-11-17", "wed": "2026-11-18", "thu": "2026-11-19",
         "fri": "2026-11-20", "sat": "2026-11-21", "sun": "2026-11-22"}
OUT: list[dict] = []


def ev(day, hhmm, type_, actor, summary, **kw):
    e = {"id": f"evt_{len(OUT) + 1:04d}", "run_id": RUN, "ts": f"{DATES[day]}T{hhmm}:00-08:00",
         "day": day, "type": type_, "actor": actor, "summary": summary}
    for k, v in kw.items():
        if v is not None:
            e[k] = v
    OUT.append(e)


def S(name, ref=None, url=None):
    s = {"name": name}
    if ref:
        s["ref"] = ref
    if url:
        s["url"] = url
    return s


def M(**kw):
    return {**kw, "currency": "USD"}


SHOPIFY_GID = "gid://shopify/Order/6123456789012"
SHOPIFY_ADMIN = "https://admin.shopify.com/store/sal-parts-dev/orders/6123456789012"

# ---------------- MON 09:12 urgent buy ----------------
ev("mon", "09:12", "repair_order.created", "tech",
   "Civic in bay 2, P0141, customer promised by 3 PM",
   reason="Intake text parsed into a repair order",
   sources=[S("SIE", "extract_intake:gliner2"), S("Shop", "RO-1042")],
   refs={"ro_id": "RO-1042"},
   data={"bay": 2, "vin": "19XFB2F59EE000000", "dtc": "P0141", "vehicle": "2014 Honda Civic 1.8L",
         "promise_time": "15:00"})
ev("mon", "09:13", "part.identified", "sal",
   "2014 Civic 1.8L, P0141 = downstream O2 sensor (bank 1 sensor 2), OEM 36532-R1A-A01",
   reason="VIN decoded by NHTSA vPIC; P0141 maps to the post-cat heater circuit in fitments",
   sources=[S("NHTSA", "vPIC decodevinvalues", "https://vpic.nhtsa.dot.gov/api/"),
            S("SingleStore", "fitments")],
   refs={"ro_id": "RO-1042", "part_no": "36532-R1A-A01"},
   data={"part_type": "o2_sensor", "position": "downstream", "year": 2014, "make": "Honda",
         "model": "Civic", "engine_l": 1.8})
ev("mon", "09:13", "context.retrieved", "sal",
   "Shop rules: R4 no-buy ValuMax, R5 counter only for urgent jobs, R7 Denso/NTK/Bosch for O2",
   sources=[S("Senso", "R4"), S("Senso", "R5"), S("Senso", "R7")],
   refs={"ro_id": "RO-1042"}, data={"kind": "rules"})
ev("mon", "09:14", "context.retrieved", "sal",
   "NHTSA: 37 complaints on 2014 Civic, 3 mention O2 / emissions (context only)",
   reason="Vehicle failure patterns, not brand quality",
   sources=[S("NHTSA", "complaintsByVehicle", "https://api.nhtsa.gov/complaints/complaintsByVehicle")],
   refs={"ro_id": "RO-1042"}, data={"kind": "complaints", "total": 37, "matching": 3})
ev("mon", "09:14", "context.retrieved", "sal",
   "Shop history: ValuMax O2 sensors came back twice in 90 days",
   sources=[S("SingleStore", "purchase_history"), S("Cognee", "fact:valumax-comebacks")],
   refs={"ro_id": "RO-1042"}, data={"kind": "brand_history", "brand": "ValuMax", "comebacks": 2})
ev("mon", "09:15", "vendors.compared", "sal",
   "5 listings across Mission, Bayshore, PartsDepot; 1 Bayshore listing is the upstream sensor",
   reason="SIE match scores vs OEM 36532-R1A-A01",
   sources=[S("Vendor", "mission"), S("Vendor", "bayshore"), S("Shopify", "partsdepot catalog"),
            S("SIE", "match_listings")],
   refs={"ro_id": "RO-1042", "part_no": "36532-R1A-A01"},
   data={"listings": [
       {"vendor_id": "mission", "vendor": "Mission Auto Supply", "brand": "Denso", "sku": "MAS-234-4364",
        "price": 41.0, "eta_minutes": 68, "verdict": "same", "score": 0.97},
       {"vendor_id": "bayshore", "vendor": "Bayshore Parts Co.", "brand": "ValuMax", "sku": "BPC-VM-O2-118",
        "price": 33.0, "eta_minutes": 50, "verdict": "same", "score": 0.91},
       {"vendor_id": "bayshore", "vendor": "Bayshore Parts Co.", "brand": "NTK", "sku": "BPC-NTK-24023",
        "price": 44.0, "eta_minutes": 358, "verdict": "same", "score": 0.95},
       {"vendor_id": "bayshore", "vendor": "Bayshore Parts Co.", "brand": "Denso", "sku": "BPC-DN-4209",
        "price": 39.0, "eta_minutes": 55, "verdict": "different", "score": 0.42},
       {"vendor_id": "partsdepot", "vendor": "PartsDepot Online", "brand": "Denso", "sku": "PD-234-4364",
        "price": 38.0, "eta_minutes": 2880, "verdict": "same", "score": 0.97}]})
ev("mon", "09:15", "part.rejected", "sal", "ValuMax O2 sensor @ Bayshore $33 rejected",
   reason="R4 no-buy list; 2 comebacks in 90 days",
   sources=[S("Senso", "R4"), S("SingleStore", "purchase_history")],
   money=M(wholesale=33), refs={"ro_id": "RO-1042", "vendor_id": "bayshore", "sku": "BPC-VM-O2-118"})
ev("mon", "09:16", "part.rejected", "sal", "Denso @ PartsDepot $38 rejected: 2-day ship",
   reason="R5: car is on a lift, urgent jobs buy from a local counter",
   sources=[S("Senso", "R5"), S("Shopify", "partsdepot")],
   money=M(wholesale=38), refs={"ro_id": "RO-1042", "vendor_id": "partsdepot", "sku": "PD-234-4364"})
ev("mon", "09:16", "part.rejected", "sal", "NTK @ Bayshore $44 rejected: ETA 3:10 PM misses the 3 PM promise",
   reason="R5: promise time must beat the bay promise",
   sources=[S("Senso", "R5"), S("Vendor", "bayshore")],
   money=M(wholesale=44), refs={"ro_id": "RO-1042", "vendor_id": "bayshore", "sku": "BPC-NTK-24023"})
ev("mon", "09:16", "part.rejected", "sal", "Denso @ Bayshore $39 rejected: listing is the upstream sensor",
   reason="SIE verdict different (score 0.42): bank 1 sensor 1, wrong position",
   sources=[S("SIE", "match_listings"), S("Vendor", "bayshore")],
   money=M(wholesale=39), refs={"ro_id": "RO-1042", "vendor_id": "bayshore", "sku": "BPC-DN-4209"})
ev("mon", "09:17", "part.chosen", "sal", "Denso 234-4364 @ Mission Auto Supply $41, ETA 10:20",
   reason="Preferred brand (R7), local counter (R5), arrives 4h40m before promise",
   sources=[S("Senso", "R7"), S("Vendor", "mission")],
   money=M(wholesale=41), refs={"ro_id": "RO-1042", "vendor_id": "mission", "sku": "MAS-234-4364"})
ev("mon", "09:18", "quote.sent", "sal", "Quote to Dana Ruiz: O2 sensor $82 + labor $95 = $177",
   reason="R2 markup, $25-75 tier x2.0",
   sources=[S("Senso", "R2"), S("Firedrill", "gmail:dana.ruiz")],
   money=M(wholesale=41, retail=82), refs={"ro_id": "RO-1042"},
   data={"lines": [{"desc": "Denso O2 sensor (downstream)", "amount": 82}, {"desc": "Labor 0.8h", "amount": 95}],
         "total": 177})
ev("mon", "09:18", "approval.requested", "sal", "Waiting on Dana Ruiz to approve $177",
   sources=[S("Firedrill", "gmail:dana.ruiz")], refs={"ro_id": "RO-1042", "approval_id": "apv_1042"})
ev("mon", "09:24", "approval.received", "car_owner", "Dana Ruiz approved the $177 repair",
   sources=[S("Firedrill", "gmail:reply")], refs={"ro_id": "RO-1042", "approval_id": "apv_1042"})
ev("mon", "09:25", "order.placed", "sal", "Counter order MAS-58213 at Mission Auto Supply, $41, ETA 10:20",
   sources=[S("Vendor", "mission:MAS-58213"), S("SingleStore", "orders")],
   money=M(wholesale=41, retail=82), refs={"ro_id": "RO-1042", "order_id": "MAS-58213", "vendor_id": "mission"},
   data={"channel": "counter", "eta": "10:20"})
ev("mon", "09:25", "payment.recorded", "sal", "Stripe test payment $177 recorded for RO-1042",
   sources=[S("Firedrill", "stripe:pi_test_1042")], money=M(retail=177), refs={"ro_id": "RO-1042"})
ev("mon", "10:18", "order.delivered", "vendor", "Mission delivered Denso O2 sensor, 2 min early",
   sources=[S("Vendor", "mission:MAS-58213")],
   refs={"ro_id": "RO-1042", "order_id": "MAS-58213", "vendor_id": "mission", "sku": "MAS-234-4364"})
ev("mon", "10:19", "sal.summary", "sal",
   "Civic part on the lift by 10:18, $82 retail on $41 cost, 4 bad options avoided",
   reason="Rejected ValuMax (R4), 2-day ship (R5), late NTK (R5), wrong-position sensor (SIE); bought Denso at Mission",
   sources=[S("Senso", "R4"), S("SingleStore", "orders")], money=M(wholesale=41, retail=82))
ev("mon", "10:19", "metrics.updated", "system", "Week so far: margin 50%, 1 order, 100% on time",
   sources=[S("SingleStore", "metrics")],
   data={"margin_pct": 50.0, "saved": 0, "on_time_pct": 100, "orders": 1, "escalations": 0,
         "variant": "control"})

# ---------------- TUE escalation + Persona ----------------
ev("tue", "11:02", "repair_order.created", "tech", "F-150 in bay 3, no-charge, alternator, promised Wed noon",
   sources=[S("SIE", "extract_intake:gliner2"), S("Shop", "RO-1043")],
   refs={"ro_id": "RO-1043"}, data={"bay": 3, "vehicle": "2016 Ford F-150 3.5L", "promise_time": "Wed 12:00"})
ev("tue", "11:04", "part.chosen", "sal", "Motorcraft alternator @ Mission $260, ETA 13:05",
   reason="Only on-time in-stock reman unit",
   sources=[S("Vendor", "mission"), S("Airbyte", "price_sheets:mission")],
   money=M(wholesale=260), refs={"ro_id": "RO-1043", "vendor_id": "mission", "sku": "MAS-GL-8758"})
ev("tue", "11:04", "escalation", "sal", "$260 alternator is over the $200 spend cap: needs owner",
   reason="R1 spend cap: single order > $200 needs owner approval",
   sources=[S("Senso", "R1")], money=M(wholesale=260),
   refs={"ro_id": "RO-1043", "escalation_id": "esc_1043"},
   data={"kind": "spend_cap", "needs": "owner", "action": "approve_order"})
ev("tue", "11:09", "identity.verified", "owner", "Owner identity verified (Maria Lopez) before $260 order",
   reason="Over-cap orders need a verified owner (R1 + KYA)",
   sources=[S("Persona", "inq_sandbox_7Hq2")], refs={"ro_id": "RO-1043", "inquiry_id": "inq_sandbox_7Hq2"},
   data={"status": "approved", "verified_name": "Maria Lopez", "method": "persona"})
ev("tue", "11:10", "approval.received", "owner", "Owner approved the $260 alternator",
   sources=[S("Shop", "owner-ui")], refs={"ro_id": "RO-1043", "approval_id": "apv_owner_1043"})
ev("tue", "11:10", "order.placed", "sal", "Counter order MAS-58240 at Mission, $260 alternator",
   sources=[S("Vendor", "mission:MAS-58240"), S("SingleStore", "orders")],
   money=M(wholesale=260, retail=390),
   refs={"ro_id": "RO-1043", "order_id": "MAS-58240", "vendor_id": "mission"},
   data={"channel": "counter", "eta": "13:05"})
ev("tue", "13:01", "order.delivered", "vendor", "Mission delivered F-150 alternator",
   sources=[S("Vendor", "mission:MAS-58240")],
   refs={"ro_id": "RO-1043", "order_id": "MAS-58240", "sku": "MAS-GL-8758"})
ev("tue", "13:02", "metrics.updated", "system", "Margin 35%, 2 orders, 1 escalation handled",
   data={"margin_pct": 35.3, "saved": 0, "on_time_pct": 100, "orders": 2, "escalations": 1,
         "variant": "control"})

# ---------------- WED 07:30 proactive restock ----------------
ev("wed", "07:30", "inventory.checked", "sal", "Checked 42 SKUs against 17 bookings in the next 7 days",
   sources=[S("SingleStore", "inventory"), S("Airbyte", "bookings")], data={"skus": 42, "bookings": 17})
ev("wed", "07:31", "stock.low", "sal", "Oil filter Civic/CR-V: have 2, need 7",
   sources=[S("SingleStore", "inventory")], refs={"sku": "FLT-15400-PLM-A02"}, data={"have": 2, "need": 7})
ev("wed", "07:31", "stock.low", "sal", "Oil filter Camry 2.5L: have 1, need 5",
   sources=[S("SingleStore", "inventory")], refs={"sku": "FLT-04152-YZZA1"}, data={"have": 1, "need": 5})
ev("wed", "07:31", "stock.low", "sal", "Wiper blades 26in: have 0, need 4",
   sources=[S("SingleStore", "inventory")], refs={"sku": "WPR-26"}, data={"have": 0, "need": 4})
ev("wed", "07:32", "restock.planned", "sal", "Restock 9 filters + 4 wipers + 6 brake cleaner = $151",
   reason="R6: $132 was $18 under the $150 free-shipping line; added brake cleaner we use weekly",
   sources=[S("Senso", "R6"), S("Shopify", "partsdepot")], money=M(wholesale=151, saved=12.99),
   data={"lines": [{"sku": "FLT-15400-PLM-A02", "qty": 5}, {"sku": "FLT-04152-YZZA1", "qty": 4},
                   {"sku": "WPR-26", "qty": 4}, {"sku": "CHM-BRAKECLN", "qty": 6}]})
ev("wed", "07:33", "order.placed", "sal", "Shopify order #1001 at PartsDepot, $151, free shipping",
   sources=[S("Shopify", SHOPIFY_GID, SHOPIFY_ADMIN)],
   money=M(wholesale=151, saved=12.99),
   refs={"order_id": SHOPIFY_GID, "vendor_id": "partsdepot"},
   data={"channel": "shopify", "shopify_order_id": SHOPIFY_GID, "admin_url": SHOPIFY_ADMIN, "fixture": True})
ev("wed", "07:34", "sal.summary", "sal", "Restocked before Thursday oil changes; shipping waived",
   sources=[S("Shopify", "order #1001")], money=M(saved=12.99))
ev("wed", "07:34", "metrics.updated", "system", "3 orders, $12.99 saved",
   data={"margin_pct": 44.1, "saved": 12.99, "on_time_pct": 100, "orders": 3, "escalations": 1,
         "variant": "control"})

# ---------------- FRI 16:00 statement ----------------
ev("fri", "16:00", "statement.parsed", "sal", "Bayshore Nov statement: 23 lines parsed from scanned PDF",
   sources=[S("SIE", "extract(output_schema)"), S("Vendor", "bayshore")],
   refs={"vendor_id": "bayshore"},
   data={"vendor_id": "bayshore", "lines": 23, "total": 1874.5, "method": "doc", "pages": 2})
ev("fri", "16:01", "escalation", "sal", "Dispute drafted: Bayshore owes $90 in 2 missing core credits",
   reason="Statement shows no credit for 2 returned cores (starter, alternator); draft not sent",
   sources=[S("SingleStore", "purchase_history"), S("SIE", "statement lines")],
   money=M(saved=90), refs={"vendor_id": "bayshore", "escalation_id": "esc_dispute_bay"},
   data={"kind": "dispute_drafted", "needs": "owner", "action": "send_dispute", "total_due": 90})

# ---------------- SUN 18:00 gets smarter ----------------
ev("sun", "18:00", "scorecard.built", "sal",
   "Bayshore late on 3 of 8 starters/alternators (37.5%), 2 missed core credits",
   sources=[S("SingleStore", "purchase_history 90d")],
   data={"per_vendor": [
       {"vendor_id": "mission", "orders": 61, "late_rate": 0.05, "missed_core_credits": 0},
       {"vendor_id": "bayshore", "orders": 54, "late_rate": 0.375, "missed_core_credits": 2},
       {"vendor_id": "partsdepot", "orders": 35, "late_rate": 0.03, "missed_core_credits": 0}]})
ev("sun", "18:01", "context.retrieved", "sal", "Cognee recall: Bayshore starter late twice on promised jobs",
   sources=[S("Cognee", "recall:bayshore")], data={"kind": "memory"})
ev("sun", "18:02", "rule.proposed", "sal", "Proposed: route starters & alternators to Mission Auto Supply",
   reason="Bayshore 37.5% late + $90 missed cores; Mission 95% on time. Projected $140/mo saved",
   sources=[S("SingleStore", "scorecard"), S("Cognee", "facts")],
   money=M(saved=140), refs={"rule_id": "R8"},
   data={"needs": "owner", "action": "approve_rule", "title": "Route starters & alternators to Mission"})
ev("sun", "18:05", "rule.approved", "owner", "Owner approved R8: starters & alternators go to Mission",
   sources=[S("Senso", "R8"), S("Shop", "owner-ui")], refs={"rule_id": "R8"},
   data={"title": "Route starters & alternators to Mission"})
ev("sun", "18:05", "memory.saved", "sal", "Remembered: owner prefers reliability over price on starters",
   sources=[S("Cognee", "remember")], refs={"rule_id": "R8"})
ev("sun", "18:05", "gate.enabled", "system", "Statsig gate sal_vendor_routing_v2 ON",
   sources=[S("Statsig", "sal_vendor_routing_v2")], refs={"rule_id": "R8"},
   data={"gate": "sal_vendor_routing_v2", "value": True})
ev("sun", "18:07", "metrics.updated", "system", "Starter replay: gate ON 100% on time vs 62.5% OFF",
   sources=[S("Statsig", "sal_vendor_routing_v2"), S("Amplitude", "agent sessions")],
   data={"margin_pct": 46.2, "saved": 242.99, "on_time_pct": 100, "orders": 3, "escalations": 1,
         "variant": "routing_v2", "compare": {"off": {"on_time_pct": 62.5}, "on": {"on_time_pct": 100}}})
ev("sun", "18:08", "sal.summary", "sal", "Week: 3 orders, 46% margin, $243 saved or recovered, 1 new rule",
   sources=[S("SingleStore", "metrics"), S("Amplitude", "dashboard")], money=M(saved=242.99))

if __name__ == "__main__":
    p = Path(__file__).with_name("sample_week.jsonl")
    p.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in OUT), encoding="utf-8")
    print(f"wrote {len(OUT)} events -> {p}")
