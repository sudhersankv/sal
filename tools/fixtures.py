"""Local fixture world for the hero week (used when db.client / seed data are unavailable).

Rows mirror contracts/db.sql. Vendors are fictional. Part numbers marked illustrative
until `data` (T1) lands verified ones in seed/. Numbers are chosen so the demo beats in
contracts/demo_script.md come out exactly (Mon $41 Denso @ Mission, Wed $132 -> +brake
cleaner x6 to clear $150, Sun Bayshore 3/8 late on starters/alternators + 2 missed cores).
"""
from __future__ import annotations

HERO_VIN = "19XFB2F58EE214879"  # NHTSA-verified by data (T1)
HERO_RO = "RO-1042"
HERO_OEM_DOWNSTREAM = "36532-R1A-A01"  # illustrative
HERO_OEM_UPSTREAM = "36531-R1A-A01"  # illustrative

VENDORS = [
    {"vendor_id": "mission", "name": "Mission Auto Supply", "kind": "counter", "cutoff_local": "17:00:00",
     "free_ship_threshold": 0.0, "account_terms": "net-30"},
    {"vendor_id": "bayshore", "name": "Bayshore Parts Co.", "kind": "counter", "cutoff_local": "16:00:00",
     "free_ship_threshold": 0.0, "account_terms": "net-30"},
    {"vendor_id": "partsdepot", "name": "PartsDepot Online", "kind": "online", "cutoff_local": "14:00:00",
     "free_ship_threshold": 150.0, "account_terms": "card"},
]

PARTS = [
    {"part_id": "o2-down-civic14", "oem_part_no": HERO_OEM_DOWNSTREAM, "part_type": "o2_sensor",
     "position": "downstream", "description": "Oxygen sensor, downstream (bank 1 sensor 2)", "has_core": 0,
     "core_charge": 0.0, "source_url": ""},
    {"part_id": "o2-up-civic14", "oem_part_no": HERO_OEM_UPSTREAM, "part_type": "o2_sensor",
     "position": "upstream", "description": "Air/fuel ratio sensor, upstream (bank 1 sensor 1)", "has_core": 0,
     "core_charge": 0.0, "source_url": ""},
    {"part_id": "alt-f150-16", "oem_part_no": "FL3T-10300-AA", "part_type": "alternator", "position": "",
     "description": "Alternator 3.5L", "has_core": 1, "core_charge": 45.0, "source_url": ""},
    {"part_id": "starter-camry18", "oem_part_no": "28100-F0010", "part_type": "starter", "position": "",
     "description": "Starter motor 2.5L", "has_core": 1, "core_charge": 45.0, "source_url": ""},
]

FITMENTS = [
    {"part_id": "o2-down-civic14", "year": 2014, "make": "HONDA", "model": "Civic", "engine_l": 1.8,
     "dtc": "P0141", "notes": "P0141 = O2 sensor heater circuit, bank 1 sensor 2 (downstream)"},
    {"part_id": "o2-up-civic14", "year": 2014, "make": "HONDA", "model": "Civic", "engine_l": 1.8,
     "dtc": "P0135", "notes": "P0135 = O2 sensor heater circuit, bank 1 sensor 1 (upstream)"},
    {"part_id": "alt-f150-16", "year": 2016, "make": "FORD", "model": "F-150", "engine_l": 3.5,
     "dtc": "", "notes": "Charging system"},
    {"part_id": "starter-camry18", "year": 2018, "make": "TOYOTA", "model": "Camry", "engine_l": 2.5,
     "dtc": "", "notes": "No-crank"},
]


def _l(vendor, sku, vpn, oem, brand, desc, price, qty, eta, variant=""):
    return {"vendor_id": vendor, "sku": sku, "vendor_part_no": vpn, "oem_part_no": oem, "brand": brand,
            "description": desc, "price": price, "qty_on_hand": qty, "eta_minutes": eta,
            "shopify_variant_id": variant}


VENDOR_CATALOG = [
    # Monday hero: downstream O2 sensor for 2014 Civic 1.8L
    _l("mission", "MAS-DEN-2344B2", "DEN 234-4B2", HERO_OEM_DOWNSTREAM, "Denso",
       "Denso O2 sensor downstream 2014 Civic 1.8L", 41.0, 3, 68),
    _l("bayshore", "BPC-VM-O2D14", "VM-O2-1418D", HERO_OEM_DOWNSTREAM, "ValuMax",
       "ValuMax economy O2 sensor rear Civic 1.8", 33.0, 6, 40),
    _l("bayshore", "BPC-NTK-25707", "NTK 25707", HERO_OEM_DOWNSTREAM, "NTK",
       "NTK oxygen sensor downstream Civic 14", 36.0, 1, 358),
    _l("bayshore", "BPC-DEN-AF14U", "DEN 234-9AF", HERO_OEM_UPSTREAM, "Denso",
       "Denso A/F sensor upstream Civic 1.8 (front)", 55.0, 2, 40),
    _l("partsdepot", "PD-DEN-2344B2", "PD-234-4B2", HERO_OEM_DOWNSTREAM, "Denso",
       "Denso Downstream Oxygen Sensor - Honda Civic 2014 1.8L", 38.0, 20, 2880, "gid://shopify/ProductVariant/0"),
    # Tuesday escalation: alternator $260
    _l("mission", "MAS-MC-ALT35", "MC GL-8925", "FL3T-10300-AA", "Motorcraft",
       "Motorcraft alternator F-150 3.5L", 260.0, 1, 75),
    _l("bayshore", "BPC-BOS-ALT35", "BOS AL-150", "FL3T-10300-AA", "Bosch",
       "Bosch reman alternator F-150 3.5", 214.0, 2, 90),
    # Sunday starter replay
    _l("mission", "MAS-DEN-STR25", "DEN 280-0F0", "28100-F0010", "Denso",
       "Denso starter Camry 2.5L", 168.0, 2, 70),
    _l("bayshore", "BPC-DEN-STR25", "DEN-STR-25C", "28100-F0010", "Denso",
       "Denso starter Camry 2.5", 152.0, 3, 60),
    # Wednesday restock consumables (online)
    _l("partsdepot", "OF-CIVIC", "PD-OF-H1", "15400-PLM-A02", "Honda", "Oil filter Civic/CR-V", 8.0, 50, 2880),
    _l("partsdepot", "OF-CRV", "PD-OF-H2", "15400-RTA-003", "Honda", "Oil filter CR-V 1.5T", 8.0, 50, 2880),
    _l("partsdepot", "OF-CAMRY", "PD-OF-T1", "04152-YZZA1", "Toyota", "Oil filter cartridge Camry 2.5", 8.0, 50, 2880),
    _l("partsdepot", "WIPER-22", "PD-WB-22", "", "Bosch", "Bosch ICON wiper blade 22in", 15.0, 40, 2880),
    _l("partsdepot", "BRK-CLN", "PD-BC-14", "", "CRC", "Brake parts cleaner 14oz", 3.5, 200, 2880),
    _l("partsdepot", "CABIN-AF", "PD-CAF-1", "", "Denso", "Cabin air filter", 14.0, 30, 2880),
]

INVENTORY = [
    {"sku": "OF-CIVIC", "name": "Oil filter Civic", "part_type": "oil_filter", "qty": 4, "min_qty": 2, "max_qty": 12},
    {"sku": "OF-CRV", "name": "Oil filter CR-V", "part_type": "oil_filter", "qty": 3, "min_qty": 2, "max_qty": 12},
    {"sku": "OF-CAMRY", "name": "Oil filter Camry", "part_type": "oil_filter", "qty": 2, "min_qty": 2, "max_qty": 12},
    {"sku": "WIPER-22", "name": "Wiper blade 22in", "part_type": "wiper", "qty": 2, "min_qty": 2, "max_qty": 10},
    {"sku": "BRK-CLN", "name": "Brake parts cleaner", "part_type": "brake_cleaner", "qty": 8, "min_qty": 4, "max_qty": 16},
    {"sku": "CABIN-AF", "name": "Cabin air filter", "part_type": "filter", "qty": 3, "min_qty": 1, "max_qty": 4},
]


def _bookings():
    rows = []
    days = ["2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-23", "2026-11-24"]
    plan = ([("OIL", "2014 Honda Civic", "OF-CIVIC")] * 5 + [("OIL", "2019 Honda CR-V", "OF-CRV")] * 4
            + [("OIL", "2018 Toyota Camry", "OF-CAMRY")] * 3)
    for i, (code, veh, sku) in enumerate(plan):
        rows.append({"booking_id": f"BK-{i + 1:03d}", "date": days[i % len(days)], "service_code": code,
                     "vehicle": veh, "parts_needed": [{"sku": sku, "qty": 1}]})
    for i, veh in enumerate(["2015 Nissan Altima", "2017 Chevrolet Silverado", "2016 Ford F-150"]):
        rows.append({"booking_id": f"BK-{20 + i}", "date": days[(i + 1) % len(days)], "service_code": "BRAKE",
                     "vehicle": veh, "parts_needed": [{"sku": "BRK-CLN", "qty": 1}]})
    for i, veh in enumerate(["2018 Toyota Camry", "2014 Honda Civic"]):
        rows.append({"booking_id": f"BK-{30 + i}", "date": days[(i + 2) % len(days)], "service_code": "WIPER",
                     "vehicle": veh, "parts_needed": [{"sku": "WIPER-22", "qty": 2}]})
    return rows


BOOKINGS = _bookings()


def _history():
    """90 days before Sun Nov 22 2026, deterministic, with the planted patterns."""
    rows = []
    n = 0

    def add(vendor, brand, ptype, day, late_min, price, comeback=0, core_due=0.0, core_rcv=0.0):
        nonlocal n
        n += 1
        placed = f"2026-{day}T09:00:00"
        hh, mm = divmod(9 * 60 + 60 + late_min, 60)
        rows.append({"order_id": f"PH-{n:04d}", "vendor_id": vendor, "brand": brand, "part_type": ptype,
                     "placed_at": placed, "promised_at": f"2026-{day}T10:00:00",
                     "delivered_at": f"2026-{day}T{hh:02d}:{mm:02d}:00", "unit_price": price,
                     "comeback": comeback, "core_credit_due": core_due, "core_credit_received": core_rcv})

    # Bayshore starters/alternators: 8 orders, 3 late, 2 missed core credits ($45 each = $90)
    bay = [("starter", "09-02", 0, 45, 45), ("alternator", "09-15", 95, 45, 0), ("starter", "09-29", 0, 45, 45),
           ("alternator", "10-08", 0, 45, 45), ("starter", "10-20", 130, 45, 45), ("alternator", "10-31", 0, 45, 0),
           ("starter", "11-07", 0, 45, 45), ("alternator", "11-13", 80, 45, 45)]
    for ptype, day, late, due, rcv in bay:
        add("bayshore", "Denso", ptype, day, late, 152.0 if ptype == "starter" else 214.0, 0, due, rcv)
    # Mission starters/alternators: 8 orders, on time, cores credited
    for i, day in enumerate(["09-05", "09-18", "10-01", "10-12", "10-24", "11-03", "11-10", "11-17"]):
        ptype = "starter" if i % 2 == 0 else "alternator"
        add("mission", "Denso", ptype, day, 0, 168.0 if ptype == "starter" else 260.0, 0, 45, 45)
    # ValuMax O2 sensors at Bayshore: 6 bought, 2 comebacks
    for i, day in enumerate(["08-28", "09-10", "09-24", "10-06", "10-27", "11-05"]):
        add("bayshore", "ValuMax", "o2_sensor", day, 0, 33.0, 1 if i in (1, 4) else 0)
    # Denso O2 at Mission: 10 bought, 0 comebacks; 1 late in 20 (Mission ~95% on time)
    for i, day in enumerate(["08-25", "09-01", "09-08", "09-16", "09-23", "10-02", "10-09", "10-16", "10-23", "11-02"]):
        add("mission", "Denso", "o2_sensor", day, 25 if i == 6 else 0, 41.0)
    # PartsDepot consumables
    for i, day in enumerate(["09-03", "09-17", "10-01", "10-15", "10-29", "11-12"]):
        add("partsdepot", "Honda", "oil_filter", day, 0, 8.0)
    return rows


PURCHASE_HISTORY = _history()

# Local copies of the Senso docs (fallback only; the real ones live in Senso, seeded by data/T1).
SHOP_RULES = [
    {"content_id": "local:R1", "title": "Spend cap", "chunk_text": "R1 Spend cap: any single order > $200 needs owner approval."},
    {"content_id": "local:R2", "title": "Markup matrix",
     "chunk_text": "R2 Markup matrix (wholesale -> retail): <=$25 x2.5, $25-75 x2.0, $75-200 x1.7, >$200 x1.5."},
    {"content_id": "local:R3", "title": "Margin target", "chunk_text": "R3 Margin target: weekly parts margin >= 45%."},
    {"content_id": "local:R4", "title": "No-buy list",
     "chunk_text": "R4 No-buy list: brand ValuMax (economy) for sensors, after comebacks."},
    {"content_id": "local:R5", "title": "Urgent job rules",
     "chunk_text": "R5 Urgent jobs (car on a lift): local counter only; promise time must beat the bay's promise time."},
    {"content_id": "local:R6", "title": "Restock rules",
     "chunk_text": "R6 Restocks: online channel preferred; bundle to clear free-shipping threshold when within $25."},
    {"content_id": "local:R7", "title": "Preferred brands by part type",
     "chunk_text": "R7 Preferred brands for O2 sensors: Denso, NTK, Bosch."},
    {"content_id": "local:R8", "title": "Shop mandate",
     "chunk_text": "R8 Never pay with a customer's card on file without explicit approval."},
]

COGNEE_FACTS = [
    "Bayshore was late on 3 of the last 8 starter/alternator deliveries.",
    "Bayshore missed 2 core credits ($45 each) in the last 90 days.",
    "ValuMax O2 sensor came back on RO-0977 and RO-1003.",
    "Mission Auto Supply delivered on time 95% of the time.",
]

COMPLAINTS_CIVIC_2014 = {
    "total": 210, "matching": 3,
    "top": [{"odi": "11000001", "date": "2019-03-04", "summary": "Check engine light, O2 sensor codes (illustrative)"}],
    "source_url": "https://api.nhtsa.gov/complaints/complaintsByVehicle?make=HONDA&model=CIVIC&modelYear=2014",
}

VIN_DECODES = {
    HERO_VIN: {"year": 2014, "make": "HONDA", "model": "Civic", "trim": "LX", "engine_l": 1.8, "cylinders": 4,
               "raw_source_url": f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{HERO_VIN}?format=json"},
}
