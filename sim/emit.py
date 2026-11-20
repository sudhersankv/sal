"""Event emission for sim. Prefers `tools.events.emit` (T2); local fallback writes the same jsonl + POSTs to UI.

The fallback validates every event against contracts/events.schema.json and never raises if the UI is down.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
UI_EVENTS_URL = os.getenv("SAL_UI_EVENTS_URL", "http://localhost:8100/events")

_lock = threading.Lock()
_validator = None
_tools_emit: Any = None  # resolved lazily; False = unavailable


def new_id() -> str:
    return "evt_" + uuid.uuid4().hex[:16]


def _schema_validator():
    global _validator
    if _validator is None:
        from jsonschema import Draft202012Validator

        schema = json.loads((ROOT / "contracts/events.schema.json").read_text(encoding="utf-8"))
        _validator = Draft202012Validator(schema)
    return _validator


def validate(event: dict) -> list[str]:
    return [e.message for e in _schema_validator().iter_errors(event)]


def log_path(run_id: str) -> Path:
    return RUNS / run_id / "events.jsonl"


def build(run_id: str, day: str, ts: str, type: str, actor: str, summary: str, **extra: Any) -> dict:
    ev: dict[str, Any] = {"id": new_id(), "run_id": run_id, "ts": ts, "day": day, "type": type,
                          "actor": actor, "summary": summary[:140]}
    if "reason" in extra and extra["reason"]:
        extra["reason"] = str(extra["reason"])[:280]
    for k, v in extra.items():
        if v is not None:
            ev[k] = v
    if "money" in ev:
        ev["money"].setdefault("currency", "USD")
    return ev


def _resolve_tools_emit():
    global _tools_emit
    if _tools_emit is None:
        if os.getenv("SIM_LOCAL_EMIT") == "1":
            _tools_emit = False
        else:
            try:
                from tools.events import emit as te  # type: ignore

                _tools_emit = te
            except Exception:
                _tools_emit = False
    return _tools_emit


def _local_write(ev: dict) -> None:
    p = log_path(ev["run_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock, p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    if os.getenv("SIM_NO_UI_POST") == "1":
        return
    try:
        import httpx

        httpx.post(UI_EVENTS_URL, json=ev, timeout=0.5)
    except Exception:
        pass  # UI down: jsonl is the source of truth


def emit(ev: dict) -> dict:
    """Emit one fully-built event. Returns the event."""
    errs = validate(ev)
    if errs:
        print(f"[sim] dropping invalid event {ev.get('type')}: {errs}", file=sys.stderr)
        return ev
    te = _resolve_tools_emit()
    if te:
        try:
            te(ev)
            return ev
        except TypeError:
            try:
                te(**ev)
                return ev
            except Exception as e:  # pragma: no cover - depends on T2
                print(f"[sim] tools.events.emit failed ({e!r}); local fallback", file=sys.stderr)
        except Exception as e:  # pragma: no cover
            print(f"[sim] tools.events.emit failed ({e!r}); local fallback", file=sys.stderr)
    _local_write(ev)
    return ev


def read_log(run_id: str) -> list[dict]:
    p = log_path(run_id)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


class Emitter:
    """Bound emitter for one run/day, stamping simulated time from a SimClock."""

    def __init__(self, run_id: str, clock):
        self.run_id = run_id
        self.clock = clock

    def __call__(self, type: str, actor: str, summary: str, *, advance_min: float = 0, **extra) -> dict:
        if advance_min:
            self.clock.advance(minutes=advance_min)
        return emit(build(self.run_id, self.clock.day, self.clock.iso(), type, actor, summary, **extra))
