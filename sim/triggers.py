"""Trigger payloads per day (contracts/demo_script.md). Seed-derived values are read lazily with fallbacks."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sim.clock import day_start, iso

ROOT = Path(__file__).resolve().parents[1]

HERO_RO = "RO-1042"
TUE_RO = "RO-1047"
HERO_CUSTOMER = "cust-dana-ruiz"
TUE_CUSTOMER = "cust-marcus-lee"
VIN_PLACEHOLDER = "<hero VIN from seed>"


def _find_in_json(obj: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and len(v) == 17:
                return v
        for v in obj.values():
            found = _find_in_json(v, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_in_json(v, keys)
            if found:
                return found
    return None


def hero_vin(root: Path = ROOT) -> str:
    """Hero VIN (NHTSA-verified 2014 Civic) from env or seed data; placeholder if seed hasn't landed."""
    if os.getenv("SAL_HERO_VIN"):
        return os.environ["SAL_HERO_VIN"]
    try:  # seed may export a constant
        from importlib import import_module

        for mod in ("seed", "seed.generate", "seed.constants"):
            try:
                v = getattr(import_module(mod), "HERO_VIN", None)
            except Exception:
                continue
            if isinstance(v, str) and len(v) == 17:
                return v
    except Exception:
        pass
    seed_dir = root / "seed"
    if seed_dir.exists():
        for p in sorted(seed_dir.rglob("*.json")):
            if p.stat().st_size > 2_000_000:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            keys = ("hero_vin", "HERO_VIN") + (("vin",) if "hero" in p.name.lower() else ())
            v = _find_in_json(data, keys)
            if v:
                return v
    return VIN_PLACEHOLDER


def statement_path(root: Path = ROOT) -> str:
    d = root / "seed" / "statements"
    if d.exists():
        files = sorted(p for p in d.iterdir() if p.is_file() and "bayshore" in p.name.lower())
        # prefer pdf > png/jpg scan > csv (the OCR / doc-extract showcase)
        for ext in (".pdf", ".png", ".jpg", ".jpeg", ".csv"):
            for p in files:
                if p.suffix.lower() == ext:
                    return p.relative_to(root).as_posix()
    return "seed/statements/bayshore_2026-11.pdf"


def trigger_for(day: str, root: Path = ROOT) -> dict[str, Any]:
    """The payload handed to `agent.sal.run_day(trigger=...)`.

    Always has: kind, day, sim_ts, text (what a human/system said), and day-specific fields.
    """
    ts = iso(day_start(day))
    if day == "mon":
        vin = hero_vin(root)
        text = f"Civic in bay 2, P0141, VIN {vin}, customer promised by 3 PM"
        return {"kind": "tech_message", "day": day, "sim_ts": ts, "actor": "tech", "text": text,
                "ro_id": HERO_RO, "bay": 2, "dtc": "P0141", "vin": vin, "promise_time": "15:00",
                "customer_id": HERO_CUSTOMER, "customer_name": "Dana Ruiz"}
    if day == "tue":
        text = "F-150 in bay 3, alternator dead, customer wants it today. Best price I see is $260."
        return {"kind": "tech_message", "day": day, "sim_ts": ts, "actor": "tech", "text": text,
                "ro_id": TUE_RO, "bay": 3, "vehicle": "2016 Ford F-150 3.5L", "part_type": "alternator",
                "quoted_wholesale": 260.0, "promise_time": "17:00", "customer_id": TUE_CUSTOMER}
    if day == "wed":
        return {"kind": "scheduled", "day": day, "sim_ts": ts, "actor": "system",
                "text": "Weekly restock check: look at the next 7 days of bookings and inventory.",
                "task": "restock", "booking_days": 7}
    if day == "fri":
        path = statement_path(root)
        return {"kind": "document", "day": day, "sim_ts": ts, "actor": "vendor",
                "text": f"Bayshore Parts Co. emailed their November statement: {path}",
                "vendor_id": "bayshore", "path": path, "task": "reconcile_statement"}
    if day == "sun":
        return {"kind": "scheduled", "day": day, "sim_ts": ts, "actor": "system",
                "text": "Weekly review: build vendor scorecards over 90 days and propose rule changes.",
                "task": "weekly_review", "days": 90}
    raise ValueError(f"no trigger for day {day!r}")
