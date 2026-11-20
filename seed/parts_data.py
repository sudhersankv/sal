"""Static catalog facts: parts, fitments, brand cross-refs. Provenance in seed/SOURCES.md.

`verified=False` rows are illustrative (shown as such in UI/README). ValuMax is fictional.
Each part: id, oem_part_no, part_type, position, description, has_core, core_charge,
source_url, verified, brands {brand: brand_part_no}, fits [(year, make, model, engine_l, dtc, notes)].
"""
from __future__ import annotations

HERO_VIN = "19XFB2F58EE214879"  # NHTSA vPIC: 2014 HONDA Civic LX 1.8L (seed/cache/nhtsa/)
HERO_PART_ID = "P-CIV14-O2-DN"
HERO_UPSTREAM_PART_ID = "P-CIV14-AF-UP"

CIVIC = (2014, "Honda", "Civic", 1.8)
F150 = (2016, "Ford", "F-150", 3.5)
CAMRY = (2018, "Toyota", "Camry", 2.5)
ALTIMA = (2015, "Nissan", "Altima", 2.5)
SILVERADO = (2017, "Chevrolet", "Silverado 1500", 5.3)
CRV = (2019, "Honda", "CR-V", 1.5)
VEHICLES = [CIVIC, F150, CAMRY, ALTIMA, SILVERADO, CRV]


def vlabel(v) -> str:
    y, mk, md, e = v
    return f"{y} {mk} {md} {e}L"


def fit(v, dtc=None, notes=""):
    return (*v, dtc, notes)


PARTS: list[dict] = [
    # ---- 2014 Honda Civic 1.8L (hero) ----
    dict(id="P-CIV14-O2-DN", oem="36532-R1B-A01", type="o2_sensor", pos="downstream",
         desc="Oxygen sensor, downstream (bank 1 sensor 2, after catalytic converter)",
         brands={"Denso": "234-4979", "NTK": "24134", "Bosch": "15009", "ValuMax": "VMX-OS4979"},
         fits=[fit(CIVIC, "P0141", "P0141 = O2 heater circuit bank 1 sensor 2 (downstream)"),
               fit(CIVIC, "P0136", "P0136 = O2 circuit bank 1 sensor 2")]),
    dict(id="P-CIV14-AF-UP", oem="36531-R1A-A01", type="o2_sensor", pos="upstream",
         desc="Air/fuel ratio sensor, upstream (bank 1 sensor 1, before catalytic converter)",
         brands={"Denso": "234-9119", "NTK": "25700"},
         fits=[fit(CIVIC, "P0135", "P0135 = A/F sensor heater circuit bank 1 sensor 1 (upstream)")]),
    dict(id="P-OIL-HON", oem="15400-PLM-A02", type="oil_filter", pos="",
         desc="Engine oil filter, spin-on (Honda 1.5T/1.8L/2.0L/2.4L)",
         brands={"Honda": "15400-PLM-A02", "WIX": "57356"},
         fits=[fit(CIVIC), fit(CRV)]),
    dict(id="P-CIV14-PAD-F", oem="45022-TR3-A02", type="brake_pads", pos="front",
         desc="Brake pad set, front, ceramic",
         brands={"Wagner": "QC1578", "Honda": "45022-TR3-A02"},
         fits=[fit(CIVIC)]),
    dict(id="P-CIV14-ROT-F", oem="45251-TR0-A00", type="brake_rotor", pos="front",
         desc="Brake rotor, front, vented", brands={"Bosch": "50011470", "Wagner": "BD126030E"},
         fits=[fit(CIVIC)]),
    dict(id="P-CIV14-AIR", oem="17220-R1A-A01", type="engine_air_filter", pos="",
         desc="Engine air filter element", brands={"Honda": "17220-R1A-A01"},
         fits=[fit(CIVIC)]),
    dict(id="P-HON-CABIN", oem="80292-SDA-407", type="cabin_air_filter", pos="",
         desc="Cabin air filter (Honda, many models)", brands={"Honda": "80292-SDA-407"},
         fits=[fit(CIVIC), fit(CRV)]),
    dict(id="P-WIPER-26", oem="", type="wiper_blade", pos="driver 26in",
         desc="Wiper blade 26 in, beam type", brands={"Bosch": "26A"},
         fits=[fit(CIVIC, notes="driver side"), fit(CAMRY, notes="driver side"), fit(CRV, notes="driver side")]),
    dict(id="P-WIPER-22", oem="", type="wiper_blade", pos="passenger 22in",
         desc="Wiper blade 22 in, beam type", brands={"Bosch": "22A"},
         fits=[fit(CIVIC, notes="passenger side")]),
    dict(id="P-WIPER-20", oem="", type="wiper_blade", pos="passenger 20in",
         desc="Wiper blade 20 in, beam type", brands={"Bosch": "20A"},
         fits=[fit(CAMRY, notes="passenger side")]),
    dict(id="P-WIPER-17", oem="", type="wiper_blade", pos="passenger 17in",
         desc="Wiper blade 17 in, beam type", brands={"Bosch": "17A"},
         fits=[fit(CRV, notes="passenger side")]),
    # ---- 2016 Ford F-150 3.5L V6 (naturally aspirated Ti-VCT) ----
    dict(id="P-F150-ALT", oem="FL3Z-10346-D", type="alternator", pos="",
         desc="Alternator, 240A, remanufactured", core=True, core_charge=45.0,
         brands={"Motorcraft": "GL-8772", "Remy": "23050"},
         fits=[fit(F150, notes="3.5L V6 non-turbo")]),
    dict(id="P-F150-STR", oem="CK4Z-11002-C", type="starter", pos="",
         desc="Starter motor, remanufactured", core=True, core_charge=45.0,
         brands={"Motorcraft": "CK4Z-11002-C", "Remy": "16198F"},
         fits=[fit(F150, notes="3.5L V6 non-turbo")]),
    dict(id="P-F150-OIL", oem="FL-500S", type="oil_filter", pos="",
         desc="Engine oil filter, spin-on", brands={"Motorcraft": "FL-500S"},
         fits=[fit(F150)]),
    dict(id="P-F150-PAD-F", oem="HL3Z-2001-A", type="brake_pads", pos="front",
         desc="Brake pad set, front", brands={"Motorcraft": "BRF-1586", "Akebono": "ACT1414"},
         fits=[fit(F150)]),
    dict(id="P-F150-BELT", oem="BR3E-8620-AB", type="serpentine_belt", pos="",
         desc="Serpentine belt", brands={"Gates": "K060930", "Motorcraft": "JK6-930"},
         fits=[fit(F150)]),
    # ---- 2018 Toyota Camry 2.5L ----
    dict(id="P-OIL-TOY", oem="04152-YZZA1", type="oil_filter", pos="",
         desc="Engine oil filter element, cartridge (with O-ring)",
         brands={"Toyota": "04152-YZZA1", "WIX": "WL10332"},
         fits=[fit(CAMRY)]),
    dict(id="P-CAM18-PAD-F", oem="04465-0E060", type="brake_pads", pos="front",
         desc="Brake pad set, front, ceramic", brands={"Wagner": "ZD2076", "Toyota": "04465-0E060"},
         fits=[fit(CAMRY)]),
    dict(id="P-CAM18-STR", oem="28100-F0060", type="starter", pos="",
         desc="Starter motor, remanufactured", core=True, core_charge=40.0,
         brands={"Toyota": "28100-F0060", "Denso": "280-0458"},
         fits=[fit(CAMRY)]),
    dict(id="P-CAM18-AIR", oem="17801-F0020", type="engine_air_filter", pos="",
         desc="Engine air filter element", brands={"Denso": "143-3611", "Bosch": "5611WS"},
         fits=[fit(CAMRY)]),
    dict(id="P-CAM18-CABIN", oem="87139-XU002", type="cabin_air_filter", pos="",
         desc="Cabin air filter", brands={"Denso": "453-2004", "Bosch": "6045C"},
         fits=[fit(CAMRY)]),
    # ---- 2015 Nissan Altima 2.5L ----
    dict(id="P-ALT15-STR", oem="23300-3TA0A", type="starter", pos="",
         desc="Starter motor, remanufactured", core=True, core_charge=40.0,
         brands={"Remy": "16198", "Nissan": "2330M-3TA0CRW", "ValuMax": "VMX-ST16198"},
         fits=[fit(ALTIMA)]),
    dict(id="P-ALT15-ALT", oem="23100-3TA1A", type="alternator", pos="",
         desc="Alternator, 110A, remanufactured", core=True, core_charge=45.0,
         brands={"Denso": "210-4003"},
         fits=[fit(ALTIMA)]),
    dict(id="P-ALT15-COIL", oem="22448-1KT1A", type="ignition_coil", pos="",
         desc="Ignition coil (coil-on-plug)", brands={"Denso": "673-4028"},
         fits=[fit(ALTIMA)]),
    dict(id="P-ALT15-PAD-F", oem="D1060-3TA0A", type="brake_pads", pos="front",
         desc="Brake pad set, front, ceramic", brands={"Akebono": "ACT1650", "Wagner": "QC1650"},
         fits=[fit(ALTIMA)]),
    dict(id="P-OIL-NIS", oem="15208-65F0E", type="oil_filter", pos="",
         desc="Engine oil filter, spin-on", brands={"Nissan": "15208-65F0E", "Bosch": "3311"},
         fits=[fit(ALTIMA)]),
    # ---- 2017 Chevrolet Silverado 1500 5.3L ----
    dict(id="P-SIL17-ALT", oem="84143543", type="alternator", pos="",
         desc="Alternator, 150A, remanufactured", core=True, core_charge=45.0,
         brands={"ACDelco": "84143543", "Denso": "210-5390"},
         fits=[fit(SILVERADO)]),
    dict(id="P-SIL17-STR", oem="12695760", type="starter", pos="",
         desc="Starter motor, remanufactured", core=True, core_charge=45.0,
         brands={"ACDelco": "12695760", "Bosch": "SR8580X"},
         fits=[fit(SILVERADO)]),
    dict(id="P-SIL17-BELT", oem="12626076", type="serpentine_belt", pos="",
         desc="Serpentine belt", brands={"Gates": "K060714"},
         fits=[fit(SILVERADO)]),
    dict(id="P-OIL-GM", oem="PF63", type="oil_filter", pos="",
         desc="Engine oil filter, spin-on", brands={"ACDelco": "PF63"},
         fits=[fit(SILVERADO)]),
    dict(id="P-SIL17-CAL-F", oem="84320931", type="brake_caliper", pos="front left",
         desc="Brake caliper, front left, remanufactured", core=True, core_charge=20.0,
         brands={"ACDelco": "172-2701", "Wagner": "TQM24046"},
         fits=[fit(SILVERADO)]),
    dict(id="P-SIL17-TIE", oem="84173385", type="tie_rod_end", pos="front outer",
         desc="Tie rod end, outer", brands={"Moog": "ES801233", "ACDelco": "45A1430"},
         fits=[fit(SILVERADO)]),
    # ---- 2019 Honda CR-V 1.5T ----
    dict(id="P-CRV19-AIR", oem="17220-5AA-A00", type="engine_air_filter", pos="",
         desc="Engine air filter element", brands={"Honda": "17220-5AA-A00", "WIX": "WA10417"},
         fits=[fit(CRV)]),
    dict(id="P-CRV19-PAD-F", oem="45022-TLA-A01", type="brake_pads", pos="front",
         desc="Brake pad set, front, ceramic", brands={"Akebono": "ACT1089A", "Wagner": "QC1089A"},
         fits=[fit(CRV)]),
    # ---- Shop consumables (no fitment) ----
    dict(id="P-BRAKLEEN", oem="05089", type="brake_cleaner", pos="",
         desc="Brakleen brake parts cleaner, non-flammable, 19 oz aerosol", brands={"CRC": "05089"},
         fits=[]),
    dict(id="P-ATF-HON", oem="08200-9008", type="atf", pos="",
         desc="Honda ATF DW-1 automatic transmission fluid, 1 qt", brands={"Honda": "08200-9008"},
         fits=[fit(CIVIC)]),
    dict(id="P-COOL-HON", oem="OL999-9011", type="coolant", pos="",
         desc="Honda Type 2 long-life coolant, premixed, 1 gal", brands={"Honda": "OL999-9011"},
         fits=[fit(CIVIC), fit(CRV)]),
    dict(id="P-COOL-TOY", oem="00272-1LLAC", type="coolant", pos="",
         desc="Toyota Super Long Life coolant, premixed, 1 gal", brands={"Toyota": "00272-1LLAC"},
         fits=[fit(CAMRY)]),
    dict(id="P-BULB-9005", oem="9005", type="bulb", pos="headlight high",
         desc="Halogen headlight bulb 9005 (HB3)", brands={"Bosch": "9005ST"},
         fits=[fit(CIVIC), fit(CAMRY)]),
    dict(id="P-BULB-7443", oem="7443", type="bulb", pos="tail/stop",
         desc="Miniature bulb 7443 (tail/stop)", brands={"Bosch": "7443"},
         fits=[fit(ALTIMA), fit(F150)]),
]



def _load_sources():
    """Map 'part_id:brand' (and part_id) -> public source URL; VERIFIED = keys confirmed by a public page.
    Research log: seed/parts_research.json (web research 2026-11-20)."""
    import json
    from pathlib import Path

    res = json.loads((Path(__file__).with_name("parts_research.json")).read_text(encoding="utf-8"))
    by_pn = {}
    for r in res:
        by_pn.setdefault(r["part_no"].replace(" ", "").upper(), r)
    src, ver = {}, set()
    for p in PARTS:
        for b, pn in p["brands"].items():
            r = by_pn.get(pn.replace(" ", "").upper())
            if r:
                src[f"{p['id']}:{b}"] = r["source_url"]
                src.setdefault(p["id"], r["source_url"])
                if r["verified"]:
                    ver.add(f"{p['id']}:{b}")
    return src, ver


SOURCES, VERIFIED = _load_sources()

BRAND_LINE = {  # counter-store line codes (vendor numbering)
    "Denso": "DEN", "NTK": "NGK", "Bosch": "BOS", "ACDelco": "ACD", "Motorcraft": "MOT", "Moog": "MOO",
    "Gates": "GAT", "Wagner": "WAG", "Akebono": "AKE", "ValuMax": "VMX", "Honda": "HON", "Toyota": "TOY",
    "Nissan": "NIS", "CRC": "CRC", "WIX": "WIX", "Remy": "REM",
}
