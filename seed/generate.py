"""Deterministic seed generator (seed=42). `build()` -> {table: [row dicts]}.

Planted demo facts live in seed/expected.py; tests/data asserts them.
Simulated week: Mon Nov 16 - Sun Nov 22 2026. History window: 90 days before Mon 09:00.
"""
from __future__ import annotations

import datetime as dt
import json
import random
from collections import defaultdict

from seed import expected as X
from seed.parts_data import (
    ALTIMA,
    BRAND_LINE,
    CAMRY,
    CIVIC,
    CRV,
    HERO_PART_ID,
    HERO_UPSTREAM_PART_ID,
    PARTS,
    SILVERADO,
    SOURCES,
    VERIFIED,
    vlabel,
)

SEED = 42
MON = dt.datetime(2026, 11, 16, 9, 0)
WED = dt.date(2026, 11, 18)
HISTORY_START = MON - dt.timedelta(days=90)
CONSUMABLE_TYPES = {"oil_filter", "wiper_blade", "brake_cleaner", "cabin_air_filter", "engine_air_filter",
                    "atf", "coolant", "bulb"}
PART = {p["id"]: p for p in PARTS}

# Wholesale base price by part type (illustrative snapshot, USD)
BASE = {"o2_sensor": 45, "oil_filter": 8.5, "brake_pads": 38, "brake_rotor": 52, "engine_air_filter": 14,
        "cabin_air_filter": 13, "wiper_blade": 14, "alternator": 210, "starter": 150, "serpentine_belt": 32,
        "ignition_coil": 48, "brake_caliper": 58, "tie_rod_end": 34, "brake_cleaner": 3.5, "atf": 9.5,
        "coolant": 21, "bulb": 9}
BRAND_MULT = {"ValuMax": 0.72, "Bosch": 1.0, "Denso": 1.0, "NTK": 1.04, "Motorcraft": 1.08, "ACDelco": 1.03,
              "Akebono": 1.12, "Wagner": 0.95, "Moog": 1.06, "Gates": 1.0, "Honda": 1.0, "Toyota": 1.0,
              "Nissan": 1.0, "CRC": 1.0}
VENDOR_MULT = {"mission": 1.12, "bayshore": 0.97, "partsdepot": 0.92}

VENDORS = [
    dict(vendor_id="mission", name="Mission Auto Supply", kind="counter", cutoff_local="17:30:00",
         free_ship_threshold=0.0,
         account_terms="Net 30 account. Counter delivery by van, 45-70 min. Core credits applied on invoice."),
    dict(vendor_id="bayshore", name="Bayshore Parts Co.", kind="counter", cutoff_local="16:30:00",
         free_ship_threshold=0.0,
         account_terms="Net 30 account. Counter delivery by van, 30-60 min quoted. Core credits on monthly statement."),
    dict(vendor_id="partsdepot", name="PartsDepot Online", kind="online", cutoff_local="15:00:00",
         free_ship_threshold=150.0,
         account_terms="Online store (Shopify). 2-day ground shipping; free shipping on orders >= $150. Net 30."),
]

CUSTOMERS = [("cust-001", "Dana Ruiz", 150.0), ("cust-002", "Marcus Lee", 300.0), ("cust-003", "Priya Shah", 250.0),
             ("cust-004", "Tom Becker", 200.0), ("cust-005", "Ana Morales", 400.0), ("cust-006", "Kevin Park", 150.0),
             ("cust-007", "Grace Okafor", 300.0), ("cust-008", "Luis Ortega", 250.0), ("cust-009", "Hannah Weiss", 200.0),
             ("cust-010", "Sam Nguyen", 350.0), ("cust-011", "Rita Gomez", 200.0), ("cust-012", "Owen Brooks", 300.0)]


def r2(x: float) -> float:
    return round(x + 1e-9, 2)


def ts(d: dt.datetime | None) -> str | None:
    return d.strftime("%Y-%m-%d %H:%M:%S") if d else None


# ---------------------------------------------------------------- vendor numbering
def vendor_ids(vendor_id: str, part: dict, brand: str, n: int) -> tuple[str, str]:
    """(sku, vendor_part_no) per vendor scheme. Same part looks different at each vendor."""
    pn = part["brands"][brand]
    line = BRAND_LINE.get(brand, brand[:3].upper())
    compact = pn.replace("-", "").replace(" ", "")
    if vendor_id == "mission":
        return f"MAS-{n:05d}", f"{line}-{compact}"
    if vendor_id == "bayshore":
        return f"BSP{100000 + n * 37:06d}", f"{line} {pn}"
    return f"PD-{line}-{compact}", pn


def listing_desc(part: dict, brand: str, vendor_id: str) -> str:
    pn = part["brands"][brand]
    fits = sorted({vlabel(f[:4]) for f in part["fits"]})
    fit_txt = (" | Fits " + ", ".join(fits)) if fits else ""
    pos = f", {part['pos']}" if part["pos"] and part["pos"] not in part["desc"] else ""
    if vendor_id == "bayshore":  # terse counter-system style
        bpos = f", {part['pos']}" if part["pos"] else ""
        kind = "A/F SENSOR" if "Air/fuel" in part["desc"] else part["type"].replace("_", " ").upper()
        return f"{brand.upper()} {pn} {kind}{bpos.upper()}{fit_txt}"
    return f"{brand} {pn} {part['desc']}{pos}{fit_txt}"


def build_catalog() -> list[dict]:
    rows: list[dict] = []
    n = 0

    def add(vendor_id, part, brand, price, qty, eta, desc=None, oem=None):
        nonlocal n
        n += 1
        sku, vpn = vendor_ids(vendor_id, part, brand, n)
        rows.append(dict(vendor_id=vendor_id, sku=sku, vendor_part_no=vpn, oem_part_no=oem or part["oem"] or pn_key(part),
                         brand=brand, description=desc or listing_desc(part, brand, vendor_id), price=r2(price),
                         qty_on_hand=qty, eta_minutes=eta, shopify_variant_id=None, embedding=None,
                         core_charge=part.get("core_charge", 0.0) if part.get("core") else 0.0,
                         _part_id=part["id"]))
        return rows[-1]

    for part in PARTS:
        pid = part["id"]
        if pid in X.CATALOG_OVERRIDES:
            continue
        brands = list(part["brands"])
        base = BASE[part["type"]]
        consumable = part["type"] in CONSUMABLE_TYPES
        for vi, vendor_id in enumerate(("mission", "bayshore", "partsdepot")):
            if vendor_id == "mission":
                vb = [b for b in brands if b != "ValuMax"]
            elif vendor_id == "bayshore":
                vb = sorted(brands, key=lambda b: BRAND_MULT.get(b, 1.0))[:2]
            else:
                vb = brands[:1] if consumable else [b for b in brands if b != "ValuMax"]
            for bi, b in enumerate(vb):
                if pid == "P-F150-ALT" and vendor_id == "bayshore":
                    continue  # Bayshore doesn't stock the F-150 alternator (TUE beat => Mission $260)
                price = base * BRAND_MULT.get(b, 1.0) * VENDOR_MULT[vendor_id] * (1 + 0.013 * ((bi + vi + len(pid)) % 5))
                if vendor_id == "partsdepot" and pid in X.PD_PRICES:
                    price = X.PD_PRICES[pid]
                if vendor_id == "mission" and pid == "P-F150-ALT" and b == "Motorcraft":
                    price = X.TUE_ALTERNATOR_PRICE
                eta = {"mission": 45 + (len(pid) * 7 + bi * 5) % 26, "bayshore": 30 + (len(pid) * 11 + bi * 7) % 31,
                       "partsdepot": 2880}[vendor_id]
                qty = {"mission": 3, "bayshore": 4, "partsdepot": 40 if consumable else 12}[vendor_id] - bi
                add(vendor_id, part, b, price, max(qty, 1), eta)

    # Hero listings (Monday) — exact numbers from contracts/demo_script.md
    hero, up = PART[HERO_PART_ID], PART[HERO_UPSTREAM_PART_ID]
    for h in X.HERO_LISTINGS:
        part = up if h["brand_part_of"] == "upstream" else hero
        desc = listing_desc(part, h["brand"], h["vendor_id"])
        row = add(h["vendor_id"], part, h["brand"], h["price"], h["qty"], h["eta"], desc=desc, oem=hero["oem"])
        row["_part_id"] = hero["id"] if part is hero else up["id"]
    return rows


def pn_key(part):
    return next(iter(part["brands"].values()))


# ---------------------------------------------------------------- inventory + bookings
def pd_sku(catalog, part_id: str) -> dict:
    part = PART[part_id]
    brand = next(iter(part["brands"]))
    sku, _ = vendor_ids("partsdepot", part, brand, 0)
    row = next(r for r in catalog if r["vendor_id"] == "partsdepot" and r["sku"] == sku)
    return row


def build_inventory(catalog) -> list[dict]:
    out = []
    for pid, (qty, mn, mx) in X.INVENTORY.items():
        row = pd_sku(catalog, pid)
        part = PART[pid]
        brand = row["brand"]
        out.append(dict(sku=row["sku"], name=f"{brand} {part['brands'][brand]} {part['desc'].split(',')[0]}"
                        + (f" ({part['pos']})" if part["pos"] else ""),
                        part_type=part["type"], qty=qty, min_qty=mn, max_qty=mx))
    return out


def build_bookings(catalog) -> list[dict]:
    sku = {pid: pd_sku(catalog, pid)["sku"] for pid in X.INVENTORY}
    oil = {CIVIC: "P-OIL-HON", CRV: "P-OIL-HON", CAMRY: "P-OIL-TOY", ALTIMA: "P-OIL-NIS", SILVERADO: "P-OIL-GM"}
    pads = {CIVIC: "P-CIV14-PAD-F", CAMRY: "P-CAM18-PAD-F", ALTIMA: "P-ALT15-PAD-F"}
    rows = []
    for i, (day, code, veh) in enumerate(X.BOOKING_PLAN, start=1):
        if code == "OIL_CHANGE":
            parts = [{"sku": sku[oil[veh]], "qty": 1}]
        elif code == "BRAKE_FRONT":
            parts = [{"sku": sku[pads[veh]], "qty": 1}, {"sku": sku["P-BRAKLEEN"], "qty": 1}]
        else:  # WIPERS (Civic: 26 + 22)
            parts = [{"sku": sku["P-WIPER-26"], "qty": 1}, {"sku": sku["P-WIPER-22"], "qty": 1}]
        rows.append(dict(booking_id=f"BK-{i:03d}", date=(WED + dt.timedelta(days=day)).isoformat(),
                         service_code=code, vehicle=vlabel(veh), parts_needed=parts))
    return rows


# ---------------------------------------------------------------- 90-day purchase history
def _biz_days(rng: random.Random, n: int, start: dt.datetime, end: dt.datetime) -> list[dt.datetime]:
    days = [start + dt.timedelta(days=i) for i in range((end - start).days)]
    days = [d for d in days if d.weekday() != 6]
    out = []
    for _ in range(n):
        d = rng.choice(days)
        out.append(d.replace(hour=rng.randint(8, 15), minute=rng.choice((0, 5, 10, 20, 30, 40, 45, 50))))
    return out


def build_history(catalog) -> dict[str, list[dict]]:
    rng = random.Random(SEED)
    by_part = defaultdict(list)
    for c in catalog:
        by_part[(c["vendor_id"], c["_part_id"])].append(c)

    def listing(vendor_id, part_id, brand=None):
        cands = [c for c in by_part[(vendor_id, part_id)] if c["brand"] != "ValuMax" or brand == "ValuMax"]
        if part_id == HERO_PART_ID:  # never the mis-listed upstream sensor
            cands = [c for c in cands if "UPSTREAM" not in c["description"].upper()]
        if brand:
            cands = [c for c in cands if c["brand"] == brand] or cands
        return cands[0]

    specs = []  # (vendor, part_id, brand, placed, late, comeback, missed_core, qty)
    # planted: Bayshore starters/alternators (8, 3 late, 2 missed cores)
    for (d, pid, brand, late, missed) in X.BAYSHORE_STARTER_ALT:
        specs.append(("bayshore", pid, brand, dt.datetime.fromisoformat(d), late, False, missed, 1))
    for (d, comeback) in X.VALUMAX_O2:
        specs.append(("bayshore", HERO_PART_ID, "ValuMax", dt.datetime.fromisoformat(d), False, comeback, False, 1))
    for (d, pid, brand) in X.MISSION_STARTER_ALT:
        specs.append(("mission", pid, brand, dt.datetime.fromisoformat(d), False, False, False, 1))

    counter_parts = [p["id"] for p in PARTS if p["type"] not in CONSUMABLE_TYPES | {"starter", "alternator"}
                     and p["id"] != HERO_UPSTREAM_PART_ID]
    consumables = [p["id"] for p in PARTS if p["type"] in CONSUMABLE_TYPES]
    end = MON.replace(hour=0) - dt.timedelta(days=1)
    n_m = X.MISSION_ORDERS - len(X.MISSION_STARTER_ALT)
    n_b = X.BAYSHORE_ORDERS - len(X.BAYSHORE_STARTER_ALT) - len(X.VALUMAX_O2)
    m_late = set(rng.sample(range(n_m), X.MISSION_LATE))
    for i, d in enumerate(_biz_days(rng, n_m, HISTORY_START, end)):
        specs.append(("mission", rng.choice(counter_parts + consumables[:3]), None, d, i in m_late, False, False, 1))
    b_late = set(rng.sample(range(n_b), X.BAYSHORE_OTHER_LATE))
    for i, d in enumerate(_biz_days(rng, n_b, HISTORY_START, end)):
        pid = rng.choice(counter_parts)
        brand = None if pid != HERO_PART_ID else rng.choice(["Denso", "NTK"])  # ValuMax O2 only via planted rows
        specs.append(("bayshore", pid, brand, d, i in b_late, False, False, 1))
    p_late = set(rng.sample(range(X.PARTSDEPOT_ORDERS), X.PARTSDEPOT_LATE))
    for i, d in enumerate(_biz_days(rng, X.PARTSDEPOT_ORDERS, HISTORY_START, end)):
        specs.append(("partsdepot", rng.choice(consumables), None, d, i in p_late, False, False, rng.choice((4, 6, 8, 10, 12))))

    specs.sort(key=lambda s: (s[3], s[0], s[1]))
    n_counter = sum(1 for s in specs if s[0] != "partsdepot")
    ro_num = X.LAST_HISTORY_RO - n_counter + 1
    seq = defaultdict(int)
    orders, lines, hist, ros = [], [], [], []
    for (vendor_id, pid, brand, placed, late, comeback, missed, qty) in specs:
        part = PART[pid]
        lst = listing(vendor_id, pid, brand)
        seq[vendor_id] += 1
        order_id = f"PO-{vendor_id[:3].upper()}-{seq[vendor_id]:04d}"
        unit = r2(lst["price"] * (1 + rng.uniform(-0.04, 0.04)))
        core = float(lst["core_charge"] or 0.0)
        if vendor_id == "partsdepot":
            promised = (placed + dt.timedelta(days=2)).replace(hour=17, minute=0)
            delivered = promised + dt.timedelta(days=1) if late else promised - dt.timedelta(hours=rng.randint(1, 6))
            ro_id, channel = None, "online"
        else:
            eta = rng.randint(45, 70) if vendor_id == "mission" else rng.randint(30, 60)
            promised = placed + dt.timedelta(minutes=eta)
            delivered = (promised + dt.timedelta(minutes=rng.randint(35, 150)) if late
                         else promised - dt.timedelta(minutes=rng.randint(0, 12)))
            ro_id, channel = f"RO-{ro_num:04d}", "counter"
            ro_num += 1
            cust = CUSTOMERS[rng.randrange(len(CUSTOMERS))][0]
            veh = vlabel(part["fits"][0][:4]) if part["fits"] else "shop supply"
            ros.append(dict(ro_id=ro_id, opened_at=ts(placed - dt.timedelta(minutes=25)), vin=None, dtc=None,
                            complaint=f"{veh}: replace {part['type'].replace('_', ' ')}"
                            + (" (COMEBACK: same symptom returned)" if comeback else ""),
                            bay=rng.randint(1, 4), customer_id=cust, status="closed"))
        due = r2(core * qty)
        received = 0.0 if missed else due
        invoice = (f"BSI-{104000 + seq[vendor_id] * 13}" if vendor_id == "bayshore"
                   else f"MAS-INV-{58000 + seq[vendor_id]}" if vendor_id == "mission" else f"#PD{1000 + seq[vendor_id]}")
        total = r2(unit * qty + core * qty)
        orders.append(dict(order_id=order_id, vendor_id=vendor_id, ro_id=ro_id, placed_at=ts(placed),
                           promised_at=ts(promised), delivered_at=ts(delivered), total=total, channel=channel,
                           external_ref=invoice, run_id="seed"))
        lines.append(dict(order_id=order_id, sku=lst["sku"], brand=lst["brand"], part_type=part["type"], qty=qty,
                          unit_price=unit, core_charge=core))
        hist.append(dict(order_id=order_id, vendor_id=vendor_id, brand=lst["brand"], part_type=part["type"],
                         placed_at=ts(placed), promised_at=ts(promised), delivered_at=ts(delivered),
                         unit_price=unit, comeback=1 if comeback else 0, core_credit_due=due,
                         core_credit_received=received))
    assert ro_num - 1 == X.LAST_HISTORY_RO
    return dict(orders=orders, order_lines=lines, purchase_history=hist, repair_orders=ros)


# ---------------------------------------------------------------- facts, rules
def build_facts(hist_tables) -> list[dict]:
    hist = hist_tables["purchase_history"]
    ros = {o["order_id"]: o["ro_id"] for o in hist_tables["orders"]}
    sa = [h for h in hist if h["vendor_id"] == "bayshore" and h["part_type"] in ("starter", "alternator")]
    late = [h for h in sa if h["delivered_at"] > h["promised_at"]]
    missed = [h for h in hist if h["core_credit_due"] > h["core_credit_received"]]
    vmx = [h for h in hist if h["brand"] == "ValuMax" and h["comeback"]]
    m = [h for h in hist if h["vendor_id"] == "mission"]
    m_on = sum(1 for h in m if h["delivered_at"] <= h["promised_at"])
    facts = [
        (f"Bayshore Parts Co. was late on {len(late)} of the last {len(sa)} starter/alternator deliveries "
         f"(orders {', '.join(h['order_id'] for h in late)}).", ["vendor:bayshore", "late", "starter", "alternator"]),
        *[(f"ValuMax downstream O2 sensor bought from Bayshore on {h['placed_at'][:10]} came back "
           f"(comeback on {ros[h['order_id']]}).", ["brand:ValuMax", "comeback", "o2_sensor"]) for h in vmx],
        *[(f"Bayshore did not credit the ${h['core_credit_due']:.0f} core on {h['order_id']} "
           f"({h['part_type']}, {h['placed_at'][:10]}).", ["vendor:bayshore", "core_credit"]) for h in missed],
        (f"Mission Auto Supply delivered {m_on} of {len(m)} orders on time in the last 90 days.",
         ["vendor:mission", "on_time"]),
        ("Dana Ruiz (2014 Civic) approves quotes up to $150 by email without a call.", ["customer:cust-001"]),
    ]
    return [dict(fact_id=f"F-{i:03d}", text=t, tags=tags, source="seed", created_at=ts(MON - dt.timedelta(hours=1)))
            for i, (t, tags) in enumerate(facts, start=1)]


def build_rules() -> list[dict]:
    from seed.senso_content import RULES

    return [dict(rule_id=rid, title=title, rule_text=text, status="active", evidence=[], senso_content_id=None,
                 created_at=ts(MON - dt.timedelta(days=30))) for rid, title, text in RULES]


def build_part_brands() -> list[dict]:
    out = []
    for p in PARTS:
        for b, pn in p["brands"].items():
            key = f"{p['id']}:{b}"
            out.append(dict(part_id=p["id"], brand=b, brand_part_no=pn,
                            illustrative=0 if (key in VERIFIED and b != "ValuMax") else 1,
                            source_url=SOURCES.get(key) or SOURCES.get(p["id"])))
    return out


def build() -> dict[str, list[dict]]:
    catalog = build_catalog()
    hist = build_history(catalog)
    parts = [dict(part_id=p["id"], oem_part_no=p["oem"] or pn_key(p), part_type=p["type"], position=p["pos"],
                  description=p["desc"], has_core=1 if p.get("core") else 0,
                  core_charge=p.get("core_charge", 0.0) if p.get("core") else 0.0,
                  source_url=SOURCES.get(p["id"])) for p in PARTS]
    fitments = [dict(part_id=p["id"], year=f[0], make=f[1], model=f[2], engine_l=f[3], dtc=f[4], notes=f[5])
                for p in PARTS for f in p["fits"]]
    cat_rows = [{k: v for k, v in c.items() if k not in ("core_charge", "_part_id")} for c in catalog]
    return dict(
        vendors=[dict(v) for v in VENDORS],
        parts=parts,
        fitments=fitments,
        part_brands=build_part_brands(),
        vendor_catalog=cat_rows,
        inventory=build_inventory(catalog),
        bookings=build_bookings(catalog),
        customers=[dict(customer_id=c, name=n, email=f"{n.split()[0].lower()}@example.com", approve_limit=a)
                   for c, n, a in CUSTOMERS],
        facts=build_facts(hist),
        rules=build_rules(),
        **hist,
    )


def catalog_core_charges() -> dict[tuple[str, str], float]:
    return {(c["vendor_id"], c["sku"]): c["core_charge"] for c in build_catalog()}


if __name__ == "__main__":
    t = build()
    print(json.dumps({k: len(v) for k, v in t.items()}, indent=1))
