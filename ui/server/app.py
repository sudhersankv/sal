"""Sal dashboard server (SPEC §7.1, §11, T5 U1).

POST /events        schema-validate, append runs/<run_id>/events.jsonl, fan out to SSE
GET  /stream        SSE; live by default. ?replay=<path>&speed=1.5 streams a recorded log instead
GET  /events        events seen this session (live) — late joiners catch up
GET  /replay        a recorded log as JSON (?path=…); the web app paces it client-side
GET  /mode          {"mode": "live"|"replay", "replay_path"}  (DEMO_MODE=replay → replay)
GET  /state         goal meters (db.client if importable, else computed from events)
POST /sim/next      proxy → SIM_URL (default http://localhost:8102); tolerates sim down
POST /sim/approve   proxy → SIM_URL
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from jsonschema import Draft202012Validator
from sse_starlette.sse import EventSourceResponse

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/events.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
RUNS = ROOT / "runs"
FIXTURE = ROOT / "ui/fixtures/sample_week.jsonl"
DEMO_LOG = RUNS / "demo/events.jsonl"
WEB_DIST = ROOT / "ui/web/dist"
SIM_URL = os.environ.get("SIM_URL", "http://localhost:8102").rstrip("/")

app = FastAPI(title="Sal UI server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_events: list[dict] = []
_subscribers: set[asyncio.Queue] = set()


# ---------------------------------------------------------------- helpers
def demo_mode() -> str:
    return "replay" if os.environ.get("DEMO_MODE", "").lower() == "replay" else "live"


def default_replay_path() -> Path:
    return DEMO_LOG if DEMO_LOG.exists() and DEMO_LOG.stat().st_size > 0 else FIXTURE


def resolve_log(path: str | None) -> Path:
    """Resolve a replay path inside the repo (no escaping ROOT)."""
    if not path:
        return default_replay_path()
    p = (ROOT / path).resolve()
    if ROOT not in p.parents or p.suffix != ".jsonl":
        raise HTTPException(400, "replay path must be a .jsonl inside the repo")
    if not p.exists():
        raise HTTPException(404, f"no such log: {path}")
    return p


def load_log(p: Path) -> list[dict]:
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def replay_delay(prev: dict | None, ev: dict, speed: float) -> float:
    """Demo pacing: steady beat, a longer pause on a new day."""
    if prev is None:
        return 0.3
    base = 2.6 if prev.get("day") != ev.get("day") else 1.1
    if ev.get("type") in ("vendors.compared", "sal.summary"):
        base += 0.6
    return base / max(speed, 0.1)


def compute_meters(events: list[dict]) -> dict[str, Any]:
    m: dict[str, Any] = {"margin_pct": None, "saved": 0.0, "on_time_pct": None, "orders": 0,
                         "escalations": 0, "variant": "control", "wholesale": 0.0, "retail": 0.0,
                         "source": "events"}
    metrics_seen = None
    delivered, on_time = 0, 0
    for e in events:
        t, money, data = e.get("type"), e.get("money") or {}, e.get("data") or {}
        if t == "order.placed":
            m["orders"] += 1
            m["wholesale"] += float(money.get("wholesale") or 0)
            m["retail"] += float(money.get("retail") or 0)
        elif t == "escalation":
            m["escalations"] += 1
        elif t == "order.delivered":
            delivered += 1
            on_time += 0 if (data.get("late") or (e.get("refs") or {}).get("late")) else 1
        elif t == "gate.enabled" and data.get("value", True):
            m["variant"] = data.get("gate", "routing_v2")
        if t == "order.placed" or (t == "escalation" and data.get("kind") == "dispute_drafted"):
            m["saved"] += float(money.get("saved") or 0)
        if t == "metrics.updated":
            metrics_seen = data
    m["saved"] = round(m["saved"], 2)
    if m["retail"]:
        m["margin_pct"] = round(100 * (m["retail"] - m["wholesale"]) / m["retail"], 1)
    if delivered:
        m["on_time_pct"] = round(100 * on_time / delivered, 1)
    if metrics_seen:  # producer-computed metrics win
        for k in ("margin_pct", "on_time_pct", "variant"):
            if metrics_seen.get(k) is not None:
                m[k] = metrics_seen[k]
        for k in ("saved", "orders", "escalations"):  # events after the last metrics event still count
            if metrics_seen.get(k) is not None:
                m[k] = max(m[k], metrics_seen[k])
        if "compare" in metrics_seen:
            m["compare"] = metrics_seen["compare"]
    return m


def db_meters() -> dict | None:
    try:
        from db import client  # type: ignore  # T1-owned; optional
    except Exception:
        return None
    for name in ("get_meters", "meters", "get_state"):
        fn = getattr(client, name, None)
        if callable(fn):
            try:
                res = fn()
                if isinstance(res, dict):
                    return {**res, "source": "db"}
            except Exception:
                return None
    return None


async def broadcast(ev: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(ev)
        except asyncio.QueueFull:
            pass


# ---------------------------------------------------------------- routes
@app.post("/events")
async def post_event(request: Request):
    try:
        ev = await request.json()
    except Exception:
        raise HTTPException(400, "body must be JSON")
    errs = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in VALIDATOR.iter_errors(ev)]
    if errs:
        return JSONResponse({"ok": False, "errors": errs}, status_code=422)
    run_dir = RUNS / str(ev["run_id"]).replace("/", "_").replace("\\", "_").replace("..", "_")
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, separators=(",", ":")) + "\n")
    _events.append(ev)
    await broadcast(ev)
    return {"ok": True, "id": ev["id"]}


@app.get("/events")
def get_events():
    return _events


@app.get("/mode")
def mode():
    rp = default_replay_path()
    return {"mode": demo_mode(), "replay_path": str(rp.relative_to(ROOT)).replace("\\", "/"),
            "sim_url": SIM_URL}


@app.get("/replay")
def replay(path: str | None = None):
    p = resolve_log(path)
    return {"path": str(p.relative_to(ROOT)).replace("\\", "/"), "events": load_log(p)}


@app.get("/stream")
async def stream(request: Request, replay: str | None = None, speed: float = 1.5):
    if replay is not None or demo_mode() == "replay":
        log = load_log(resolve_log(replay or None))

        async def replay_gen():
            prev = None
            for ev in log:
                await asyncio.sleep(replay_delay(prev, ev, speed))
                if await request.is_disconnected():
                    return
                prev = ev
                yield {"event": "sal", "id": ev.get("id"), "data": json.dumps(ev)}
            yield {"event": "end", "data": "{}"}

        return EventSourceResponse(replay_gen())

    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _subscribers.add(q)

    async def live_gen():
        try:
            for ev in list(_events):  # catch up
                yield {"event": "sal", "id": ev.get("id"), "data": json.dumps(ev)}
            while True:
                ev = await q.get()
                yield {"event": "sal", "id": ev.get("id"), "data": json.dumps(ev)}
        finally:
            _subscribers.discard(q)

    return EventSourceResponse(live_gen(), ping=15)


@app.get("/state")
def state(replay: str | None = None):
    if replay is not None:
        return {"meters": compute_meters(load_log(resolve_log(replay or None)))}
    meters = db_meters() or compute_meters(_events)
    return {"meters": meters, "events": len(_events), "mode": demo_mode()}


async def _proxy(path: str, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(f"{SIM_URL}{path}", json=body)
        try:
            payload = r.json()
        except Exception:
            payload = {"text": r.text}
        return JSONResponse({"ok": r.is_success, "sim": payload}, status_code=200 if r.is_success else 502)
    except httpx.HTTPError as e:
        return JSONResponse({"ok": False, "offline": True, "error": f"sim unreachable: {type(e).__name__}"},
                            status_code=503)


@app.post("/sim/next")
async def sim_next(request: Request):
    return await _proxy("/sim/next", request)


@app.post("/sim/approve")
async def sim_approve(request: Request):
    return await _proxy("/sim/approve", request)


@app.get("/healthz")
def healthz():
    return {"ok": True}


# Built web app (npm run build) served from the same port for the demo.
if WEB_DIST.exists():
    @app.get("/{full_path:path}")
    def spa(full_path: str):
        f = (WEB_DIST / full_path).resolve()
        if full_path and WEB_DIST in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(WEB_DIST / "index.html")
