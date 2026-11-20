"""Sim control API (S2). Run: `uv run uvicorn sim.api:app --port 8102`. ui/server proxies to it.

POST /sim/next              advance to the next day (mon->tue->wed->fri->sun) and run it in the background
     body (optional): {"run_id": "...", "variant": "on"|"off", "day": "mon", "reset": true}
POST /sim/approve           {"kind": "quote"|"order"|"rule"|"identity", "id": "<ro_id|rule_id>", "approved": true}
GET  /sim/state             current day, running flag, run_id, pending approvals, last results
GET  /sim/approvals         all approvals (pending + decided)
"""
from __future__ import annotations

import os
import threading
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sim.actors import ACTORS, KINDS, configure
from sim.clock import WEEK_ORDER, next_day

app = FastAPI(title="Sal sim", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_state: dict[str, Any] = {"run_id": None, "day": None, "running": False, "results": [], "error": None,
                          "interactive": os.getenv("SIM_INTERACTIVE", "1") == "1"}
_lock = threading.Lock()


class NextBody(BaseModel):
    run_id: str | None = None
    variant: str | None = None
    day: str | None = None
    reset: bool = False


class ApproveBody(BaseModel):
    kind: str
    id: str
    approved: bool = True


def _worker(day: str, run_id: str, variant: str | None) -> None:
    from sim.run import run_day

    try:
        res = run_day(day, run_id, variant)
        _state["results"].append(res)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _state["error"] = f"{day}: {e!r}"
    finally:
        _state["running"] = False


@app.post("/sim/next")
def sim_next(body: NextBody | None = None) -> dict:
    body = body or NextBody()
    with _lock:
        if _state["running"]:
            raise HTTPException(409, f"{_state['day']} is still running")
        if body.reset or body.run_id and body.run_id != _state["run_id"]:
            from sim import flags
            from sim.run import default_run_id

            flags.clear_override()
            _state.update(run_id=body.run_id or default_run_id("ui"), day=None, results=[], error=None)
        if _state["run_id"] is None:
            from sim.run import default_run_id

            _state["run_id"] = default_run_id("ui")
        day = body.day or next_day(_state["day"])
        if day is None:
            return {"done": True, **public_state()}
        if day not in WEEK_ORDER:
            raise HTTPException(400, f"day must be one of {WEEK_ORDER}")
        configure(interactive=_state["interactive"])
        _state.update(day=day, running=True, error=None)
        threading.Thread(target=_worker, args=(day, _state["run_id"], body.variant), daemon=True).start()
    return {"started": day, **public_state()}


@app.post("/sim/approve")
def sim_approve(body: ApproveBody) -> dict:
    if body.kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {KINDS}")
    a = ACTORS.decide(body.kind, body.id, body.approved)
    return {"ok": True, "approval": a.public() if a else None}


@app.get("/sim/approvals")
def sim_approvals() -> dict:
    return {"approvals": ACTORS.all()}


def public_state() -> dict:
    return {"run_id": _state["run_id"], "day": _state["day"], "running": _state["running"],
            "next_day": next_day(_state["day"]) if not _state["running"] else None,
            "interactive": _state["interactive"], "pending": ACTORS.pending(),
            "results": _state["results"], "error": _state["error"]}


@app.get("/sim/state")
def sim_state() -> dict:
    return public_state()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}
