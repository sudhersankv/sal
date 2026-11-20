"""SalEvent emission (SPEC §7.1, X4).

`emit(type, summary, **fields)` builds an event, validates it against contracts/events.schema.json,
always appends it to runs/<run_id>/events.jsonl, and POSTs to the UI (SAL_UI_URL, default
http://localhost:8100/events). Never raises: an invalid event is repaired (summary/reason truncated,
unknown source names dropped) or logged as a `type=error` line instead.
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from pathlib import Path

from jsonschema import Draft202012Validator

from tools import context

log = logging.getLogger("sal-tools.events")
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/events.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
SOURCE_NAMES = set(SCHEMA["properties"]["sources"]["items"]["properties"]["name"]["enum"])
_ALPH = "0123456789abcdefghjkmnpqrstvwxyz"
_lock = threading.RLock()
_last_ms = 0
_seq = 0


def new_id() -> str:
    """evt_<ulid-ish>: 10 chars of ms time + 2-char counter + 6 random, lowercase base32 (sortable)."""
    global _last_ms, _seq
    with _lock:
        ms = int(time.time() * 1000)
        _seq = _seq + 1 if ms == _last_ms else 0
        _last_ms = ms
        t = "".join(_ALPH[(ms >> (5 * i)) & 31] for i in reversed(range(10)))
        s = _ALPH[(_seq >> 5) & 31] + _ALPH[_seq & 31]
        r = "".join(random.choice(_ALPH) for _ in range(6))
    return f"evt_{t}{s}{r}"


def _clean_sources(sources):
    out = []
    for s in sources or []:
        if isinstance(s, str):
            s = {"name": s}
        if isinstance(s, dict) and s.get("name") in SOURCE_NAMES:
            out.append({k: str(v) for k, v in s.items() if k in ("name", "ref", "url") and v is not None})
    return out


def build(type: str, summary: str, *, actor: str = "sal", **fields) -> dict:
    evt = {"id": fields.pop("id", None) or new_id(), "run_id": fields.pop("run_id", None) or context.run_id(),
           "ts": fields.pop("ts", None) or context.ts(), "day": fields.pop("day", None) or context.day(),
           "type": type, "actor": actor, "summary": (summary or type)[:140]}
    if fields.get("reason"):
        evt["reason"] = str(fields.pop("reason"))[:280]
    fields.pop("reason", None)
    if fields.get("sources"):
        evt["sources"] = _clean_sources(fields.pop("sources"))
    fields.pop("sources", None)
    money = fields.pop("money", None)
    if money:
        evt["money"] = {**{k: float(v) for k, v in money.items() if k != "currency" and v is not None},
                        "currency": "USD"}
    for k in ("refs", "data"):
        v = fields.pop(k, None)
        if v:
            evt[k] = v
    if fields:  # loose extras go to data
        evt.setdefault("data", {}).update(fields)
    return json.loads(json.dumps(evt, default=str))


def _append(evt: dict) -> None:
    p = context.runs_dir() / evt["run_id"] / "events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock, p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evt, ensure_ascii=False) + "\n")


def _post(evt: dict) -> None:
    if os.environ.get("SAL_EVENTS_POST", "1") == "0":
        return
    url = os.environ.get("SAL_UI_URL", "http://localhost:8100") + "/events"
    try:
        import httpx
        httpx.post(url, json=evt, timeout=float(os.environ.get("SAL_EVENTS_TIMEOUT", "0.5")))
    except Exception as e:  # noqa: BLE001 - UI down is fine; jsonl is the record
        log.debug("event POST failed (%s); kept in jsonl", e)


def emit(type: str, summary: str, **fields) -> dict:
    """Build, validate, append to jsonl, POST. Returns the event (or the error event). Never raises."""
    try:
        evt = build(type, summary, **fields)
        errs = [e.message for e in VALIDATOR.iter_errors(evt)]
        if errs:
            log.warning("invalid event %s: %s", type, errs)
            evt = build("error", f"invalid {type} event"[:140], actor="system",
                        reason="; ".join(errs)[:280], data={"original_type": str(type)})
        _append(evt)
        _post(evt)
        return evt
    except Exception as e:  # noqa: BLE001
        log.error("emit failed: %s", e)
        return {"id": "", "error": str(e)}


def emit_raw(evt: dict) -> dict:
    """emit_event tool: partial SalEvent → filled + validated."""
    evt = dict(evt or {})
    t = evt.pop("type", "sal.summary")
    s = evt.pop("summary", t)
    return emit(t, s, **evt)
