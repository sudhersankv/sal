"""NHTSA vPIC + complaints (no key). Reads seed/cache/nhtsa/ first, then live, writes runs/cache/nhtsa/."""

from __future__ import annotations

import json
import re

import httpx

from ._common import SEED, cache_get, cache_put, key_for, replay, safe_exc

SERVICE = "nhtsa"
SEED_CACHE = SEED / "cache" / "nhtsa"
VPIC = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{vin}?format=json{my}"
COMPLAINTS = "https://api.nhtsa.gov/complaints/complaintsByVehicle?make={make}&model={model}&modelYear={year}"


def available() -> bool:
    return True


def _seed_get(*names: str) -> dict | None:
    for n in names:
        p = SEED_CACHE / n
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None


def _fetch(url: str, key: str, seed_names: list[str]) -> tuple[dict | None, str]:
    raw = _seed_get(*seed_names)
    if raw is not None:
        return raw, "seed_cache"
    hit = cache_get(SERVICE, key)
    if hit is not None and replay():
        return hit, "cache"
    try:
        r = httpx.get(url, timeout=20, headers={"User-Agent": "sal-demo/0.1"})
        r.raise_for_status()
        raw = r.json()
        cache_put(SERVICE, key, raw)
        return raw, "live"
    except Exception as e:
        if hit is not None:
            return hit, "cache"
        return {"_error": safe_exc(e)}, "error"


def _f(x) -> float | None:
    try:
        return round(float(x), 1)
    except (TypeError, ValueError):
        return None


def _i(x) -> int | None:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def decode_vin(vin: str, model_year: int | None = None) -> dict:
    vin = (vin or "").strip().upper()
    url = VPIC.format(vin=vin, my=f"&modelyear={model_year}" if model_year else "")
    raw, src = _fetch(url, key_for("vin", vin, model_year), [f"vin_{vin}.json", f"{vin}.json"])
    if src == "error":
        return {"error": {"code": "nhtsa_unreachable", "message": raw.get("_error", "")}}
    res = (raw.get("Results") or [{}])[0]
    if not res.get("Make"):
        return {"error": {"code": "decode_failed", "message": res.get("ErrorText", "no make decoded")[:200]}}
    return {
        "year": _i(res.get("ModelYear")),
        "make": (res.get("Make") or "").title(),
        "model": res.get("Model") or "",
        "trim": res.get("Trim") or "",
        "engine_l": _f(res.get("DisplacementL")),
        "cylinders": _i(res.get("EngineCylinders")),
        "raw_source_url": url,
        "source": src,
    }


def complaints(make: str, model: str, year: int, component_keyword: str | None = None, top: int = 5) -> dict:
    url = COMPLAINTS.format(make=make, model=model, year=year)
    slug = re.sub(r"[^a-z0-9]+", "_", f"{make}_{model}_{year}".lower())
    raw, src = _fetch(url, key_for("complaints", make.lower(), model.lower(), year), [f"complaints_{slug}.json"])
    if src == "error":
        return {"error": {"code": "nhtsa_unreachable", "message": raw.get("_error", "")}}
    rows = raw.get("results") or raw.get("Results") or []
    kw = (component_keyword or "").lower()
    kws = [k for k in re.split(r"[\s,/]+", kw) if k]

    def match(r: dict) -> bool:
        if not kws:
            return True
        blob = f"{r.get('components', '')} {r.get('summary', '')}".lower()
        return any(k in blob for k in kws)

    matching = [r for r in rows if match(r)]
    return {
        "total": len(rows),
        "matching": len(matching),
        "top": [
            {
                "odi": r.get("odiNumber"),
                "date": r.get("dateComplaintFiled") or r.get("dateOfIncident"),
                "summary": (r.get("summary") or "")[:400],
                "components": r.get("components"),
            }
            for r in matching[:top]
        ],
        "source_url": url,
        "source": src,
    }
