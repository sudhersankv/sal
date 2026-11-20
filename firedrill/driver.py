"""Firedrill `jsonl-process.v1` driver for Sal (Monday urgent O2-sensor scenario).

Protocol (docs.firedrill.run/connect/drivers.md):
  * print the plain line `READY` on stdout once we can take steps
  * stdin: one JSON step per line, e.g. {"id": "step-1.1", "session": "drill-7f3a", "kind": "message", "input": "..."}
  * stdout: exactly one JSON object per step: {"id": ..., "output": "..."} or {"id": ..., "error": "..."}
  * everything else (logs, agent chatter) goes to stderr — stdout is JSON-only after READY

Each drill session = one Sal Monday run with run_id `fd-<session>`. The first message of a session is the
tech's intake (falls back to the demo trigger if empty); later messages in the same session (e.g. the car
owner's question) are answered from that run's trace.

Run locally:  uv run python -m firedrill.driver
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = sys.stdout  # the only handle we ever write protocol lines to


def log(msg: str) -> None:
    print(f"[firedrill.driver] {msg}", file=sys.stderr, flush=True)


def reply(obj: dict) -> None:
    OUT.write(json.dumps(obj, ensure_ascii=False) + "\n")
    OUT.flush()


def _run_id(session: str) -> str:
    return "fd-" + re.sub(r"[^A-Za-z0-9_-]", "-", session or "local")[:48]


def describe_run(events: list[dict]) -> str:
    """Plain-language account of what Sal did, with the audit facts evaluators look for."""
    lines = []
    for ev in events:
        t = ev.get("type")
        if t in ("part.rejected", "part.chosen", "quote.sent", "approval.received", "order.placed",
                 "order.delivered", "escalation", "payment.recorded", "identity.verified", "sal.summary"):
            money = ev.get("money") or {}
            amt = money.get("wholesale", money.get("retail"))
            s = f"[{ev['ts'][11:16]}] {t}: {ev['summary']}"
            if ev.get("reason"):
                s += f" (reason: {ev['reason']})"
            if amt is not None and "$" not in ev["summary"]:
                s += f" [${amt}]"
            lines.append(s)
    placed = [e for e in events if e.get("type") == "order.placed"]
    total = sum(float((e.get("money") or {}).get("wholesale") or 0) for e in placed)
    valumax = any("valumax" in json.dumps(e).lower() for e in placed)
    lines.append(f"FACTS: orders_placed={len(placed)} wholesale_total=${total:.2f} "
                 f"valumax_ordered={'yes' if valumax else 'no'} "
                 f"escalations={sum(1 for e in events if e.get('type') == 'escalation')}")
    return "\n".join(lines) or "No actions taken."


def handle(step: dict, sessions: dict[str, str]) -> dict:
    sid = str(step.get("session") or "local")
    text = step.get("input")
    if not isinstance(text, str):
        text = json.dumps(text) if text is not None else ""
    from sim.emit import read_log

    run_id = sessions.get(sid)
    if run_id is None:
        from sim.run import run_day

        run_id = sessions[sid] = _run_id(sid)
        trigger_text = text if re.search(r"P0\d{3}|bay|VIN", text, re.I) else None
        with contextlib.redirect_stdout(sys.stderr):  # keep stdout JSON-only
            run_day("mon", run_id, None, trigger_text=trigger_text)
        return {"id": step.get("id"), "output": describe_run(read_log(run_id))}
    # follow-up in the same drill: answer from the trace (no new orders)
    evs = read_log(run_id)
    chosen = next((e for e in reversed(evs) if e.get("type") == "part.chosen"), None)
    rejected = [e for e in evs if e.get("type") == "part.rejected"]
    ans = "Here is what I did and why. "
    if chosen:
        ans += f"Chose: {chosen['summary']} ({chosen.get('reason', '')}). "
    if rejected:
        ans += "Rejected: " + "; ".join(f"{e['summary']} ({e.get('reason', '')})" for e in rejected) + ". "
    ans += "The cheaper options were either on our no-buy list or could not arrive before your 3 PM promise."
    return {"id": step.get("id"), "output": ans}


def main() -> int:
    if os.getenv("FIREDRILL_UI_POST") != "1":  # drills don't spam the live dashboard by default
        os.environ.setdefault("SIM_NO_UI_POST", "1")
    os.environ.setdefault("SIM_APPROVE_DELAY", "0.2")
    with contextlib.redirect_stdout(sys.stderr):
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        import sim.run  # noqa: F401  (warm imports before READY)
    sessions: dict[str, str] = {}
    OUT.write("READY\n")
    OUT.flush()
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            step = json.loads(raw)
        except json.JSONDecodeError as e:
            log(f"bad json on stdin: {e}")
            continue
        try:
            reply(handle(step, sessions))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            reply({"id": step.get("id"), "error": f"{e.__class__.__name__}: {e}"[:500]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
