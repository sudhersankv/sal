"""Planted demo numbers (contracts/demo_script.md). Generator reads these; tests assert them.
Other streams may import these constants for their own tests.
"""
from __future__ import annotations

from seed.parts_data import ALTIMA, CAMRY, CIVIC, CRV, SILVERADO

# ---- MON hero (2014 Civic, P0141 -> downstream O2) ------------------------------------------
HERO_RO = "RO-1042"
HERO_CUSTOMER = "cust-001"  # Dana Ruiz
HERO_DTC = "P0141"
# Listings for the hero OEM no. `brand_part_of=upstream` = Bayshore's mis-cross-referenced
# upstream A/F sensor (carries the downstream OEM no, but description says upstream -> "different").
HERO_LISTINGS = [
    dict(vendor_id="mission", brand="Denso", price=41.00, qty=2, eta=68, brand_part_of="downstream"),  # 09:12 -> 10:20
    dict(vendor_id="mission", brand="NTK", price=47.50, qty=1, eta=68, brand_part_of="downstream"),
    dict(vendor_id="mission", brand="Bosch", price=44.25, qty=1, eta=68, brand_part_of="downstream"),
    dict(vendor_id="bayshore", brand="ValuMax", price=33.00, qty=5, eta=40, brand_part_of="downstream"),
    dict(vendor_id="bayshore", brand="NTK", price=39.00, qty=1, eta=358, brand_part_of="downstream"),  # 09:12 -> 15:10
    dict(vendor_id="bayshore", brand="Denso", price=52.00, qty=2, eta=40, brand_part_of="upstream"),
    dict(vendor_id="partsdepot", brand="Denso", price=38.00, qty=12, eta=2880, brand_part_of="downstream"),
    dict(vendor_id="partsdepot", brand="NTK", price=40.50, qty=6, eta=2880, brand_part_of="downstream"),
]
CATALOG_OVERRIDES = {"P-CIV14-O2-DN", "P-CIV14-AF-UP"}  # listed only via HERO_LISTINGS
HERO_CHOSEN = dict(vendor_id="mission", brand="Denso", price=41.00, eta_local="10:20")

# ---- TUE escalation beat --------------------------------------------------------------------
TUE_ALTERNATOR_PRICE = 260.00  # Motorcraft F-150 alternator @ Mission (> $200 spend cap)

# ---- WED restock ----------------------------------------------------------------------------
# PartsDepot prices for restocked consumables (6*8.50 + 3*9.00 + 2*14 + 2*13 = 132.00)
PD_PRICES = {"P-OIL-HON": 8.50, "P-OIL-TOY": 9.00, "P-WIPER-26": 14.00, "P-WIPER-22": 13.00,
             "P-BRAKLEEN": 3.50}
# inventory: part_id -> (qty, min_qty, max_qty); inventory.sku == PartsDepot sku
INVENTORY = {
    "P-OIL-HON": (3, 2, 12), "P-OIL-TOY": (1, 1, 8), "P-OIL-NIS": (4, 1, 6), "P-OIL-GM": (3, 1, 6),
    "P-F150-OIL": (2, 1, 6), "P-WIPER-26": (0, 0, 4), "P-WIPER-22": (0, 0, 4), "P-WIPER-20": (1, 0, 4),
    "P-WIPER-17": (1, 0, 4), "P-BRAKLEEN": (8, 4, 24), "P-CIV14-PAD-F": (2, 1, 4), "P-CAM18-PAD-F": (2, 1, 4),
    "P-ALT15-PAD-F": (2, 1, 4), "P-HON-CABIN": (3, 1, 6), "P-CAM18-CABIN": (2, 1, 4), "P-CIV14-AIR": (2, 1, 4),
    "P-CRV19-AIR": (2, 1, 4), "P-CAM18-AIR": (2, 1, 4), "P-ATF-HON": (8, 4, 16), "P-COOL-HON": (3, 1, 6),
    "P-COOL-TOY": (2, 1, 6), "P-BULB-9005": (4, 2, 8), "P-BULB-7443": (6, 2, 10),
}
# bookings: (days after Wed Nov 18, service_code, vehicle). 7-day window = day 0..6.
BOOKING_PLAN = [
    (0, "OIL_CHANGE", CIVIC), (0, "OIL_CHANGE", CAMRY), (0, "BRAKE_FRONT", CAMRY),
    (1, "OIL_CHANGE", CRV), (1, "WIPERS", CIVIC), (1, "OIL_CHANGE", ALTIMA),
    (2, "OIL_CHANGE", CIVIC), (2, "BRAKE_FRONT", ALTIMA), (2, "OIL_CHANGE", CAMRY),
    (3, "OIL_CHANGE", CRV), (3, "OIL_CHANGE", SILVERADO),
    (4, "OIL_CHANGE", CIVIC), (4, "BRAKE_FRONT", CIVIC), (4, "WIPERS", CIVIC),
    (5, "OIL_CHANGE", CRV), (5, "OIL_CHANGE", CAMRY),
    (6, "OIL_CHANGE", CIVIC),
    # outside the 7-day window (noise; restock math holds with or without them)
    (7, "OIL_CHANGE", ALTIMA), (8, "OIL_CHANGE", SILVERADO),
]
BOOKING_WINDOW_DAYS = 7
# Restock formula (documented for tools/plan_restock):
#   need  = sum(parts_needed.qty) over bookings with Wed <= date < Wed+7
#   order_qty = max(0, need + min_qty - qty)
EXPECTED_RESTOCK = {"P-OIL-HON": 6, "P-OIL-TOY": 3, "P-WIPER-26": 2, "P-WIPER-22": 2}
EXPECTED_RESTOCK_FILTERS = 9
EXPECTED_RESTOCK_WIPERS = 4
EXPECTED_RESTOCK_TOTAL = 132.00
FREE_SHIP_THRESHOLD = 150.00
BUNDLE_ADDON = ("P-BRAKLEEN", 6)  # 6 * 3.50 = 21.00 -> 153.00 >= 150

# ---- History (90 days) ----------------------------------------------------------------------
MISSION_ORDERS, MISSION_LATE = 40, 2          # 95% on time
BAYSHORE_ORDERS, BAYSHORE_OTHER_LATE = 60, 5
PARTSDEPOT_ORDERS, PARTSDEPOT_LATE = 50, 2
TOTAL_ORDERS = MISSION_ORDERS + BAYSHORE_ORDERS + PARTSDEPOT_ORDERS  # 150
LAST_HISTORY_RO = 1041
# (placed_at, part_id, brand, late, missed_core_credit)
BAYSHORE_STARTER_ALT = [
    ("2026-08-24 10:05", "P-ALT15-STR", "Denso", False, False),
    ("2026-09-08 09:40", "P-SIL17-ALT", "ACDelco", True, False),
    ("2026-09-21 13:20", "P-CAM18-STR", "Denso", False, False),
    ("2026-10-02 11:10", "P-ALT15-ALT", "Denso", False, False),
    ("2026-10-13 08:50", "P-F150-STR", "Motorcraft", True, False),
    ("2026-10-22 14:30", "P-F150-STR", "Motorcraft", False, True),
    ("2026-11-03 10:45", "P-SIL17-ALT", "ACDelco", True, True),
    ("2026-11-11 09:15", "P-ALT15-STR", "Denso", False, False),
]
BAYSHORE_SA_LATE, BAYSHORE_SA_TOTAL = 3, 8   # 37.5%
MISSED_CORE_CREDITS, MISSED_CORE_TOTAL = 2, 90.00
# (placed_at, comeback)
VALUMAX_O2 = [("2026-08-20 09:30", False), ("2026-09-15 10:20", True), ("2026-10-06 15:05", True)]
VALUMAX_O2_COMEBACKS = 2
MISSION_STARTER_ALT = [("2026-08-31 10:00", "P-SIL17-STR", "ACDelco"), ("2026-09-29 13:00", "P-ALT15-STR", "Denso"),
                       ("2026-10-27 09:30", "P-F150-ALT", "Motorcraft"), ("2026-11-09 11:45", "P-CAM18-STR", "Denso")]

# ---- FRI statement --------------------------------------------------------------------------
STATEMENT_VENDOR = "bayshore"
STATEMENT_DATE = "2026-11-15"
STATEMENT_PERIOD = ("2026-10-16", "2026-11-15")
