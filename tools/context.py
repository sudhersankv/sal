"""Run context for sal-tools: run_id, simulated day and clock.

Sources (first wins): in-process `set_context()`, `runs/<run_id>/clock.json` ({"ts", "day"}, written by sim
to advance the clock while the MCP subprocess runs), env SAL_RUN_ID / SAL_DAY / SAL_SIM_TS / SAL_VARIANT.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DEFAULT_TS = {"mon": "2026-11-16T09:12:00-08:00", "tue": "2026-11-17T10:00:00-08:00",
              "wed": "2026-11-18T07:30:00-08:00", "thu": "2026-11-19T09:00:00-08:00",
              "fri": "2026-11-20T16:00:00-08:00", "sat": "2026-11-21T09:00:00-08:00",
              "sun": "2026-11-22T18:00:00-08:00"}
_override: dict = {}


def set_context(**kw) -> None:
    """kw: run_id, day, ts, variant. None values clear the override."""
    for k, v in kw.items():
        if v is None:
            _override.pop(k, None)
        else:
            _override[k] = v


def runs_dir() -> Path:
    return Path(os.environ.get("SAL_RUNS_DIR") or ROOT / "runs")


def run_id() -> str:
    return _override.get("run_id") or os.environ.get("SAL_RUN_ID") or "dev"


def _clock_file() -> dict:
    p = runs_dir() / run_id() / "clock.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}


def day() -> str:
    d = _override.get("day") or _clock_file().get("day") or os.environ.get("SAL_DAY")
    if d in DAYS:
        return d
    if _override.get("ts") or os.environ.get("SAL_SIM_TS"):
        return DAYS[now().weekday()]
    return "mon"


def now() -> datetime:
    ts = _override.get("ts")
    if not ts and _override.get("day") in DEFAULT_TS:
        ts = DEFAULT_TS[_override["day"]]
    ts = ts or _clock_file().get("ts") or os.environ.get("SAL_SIM_TS")
    if not ts:
        d = _override.get("day") or os.environ.get("SAL_DAY") or "mon"
        ts = DEFAULT_TS.get(d, DEFAULT_TS["mon"])
    return datetime.fromisoformat(ts)


def ts() -> str:
    return now().isoformat()


def plus_minutes(minutes: float) -> str:
    return (now() + timedelta(minutes=minutes)).isoformat()


def variant() -> str:
    """Statsig arm chosen by sim (never by Sal): 'on' means sal_vendor_routing_v2 ON."""
    return (_override.get("variant") or os.environ.get("SAL_VARIANT") or "off").lower()
