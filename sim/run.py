"""Week runner (SPEC §12 T4/S1).

    python -m sim.run --day mon [--variant on|off] [--run-id X] [--interactive]
    python -m sim.run --week [--run-id demo]          # mon -> tue -> wed -> fri -> sun

Env knobs: SIM_STUB_AGENT=1 (force scripted agent), SIM_APPROVE_DELAY (s, default 1.0),
SIM_OFFLINE=1 (skip Statsig network), SIM_LOCAL_EMIT=1 (skip tools.events), SAL_HERO_VIN.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable

from dotenv import load_dotenv

from sim import flags, metrics
from sim.actors import ACTORS, configure
from sim.clock import WEEK_ORDER, SimClock
from sim.emit import Emitter, read_log
from sim.triggers import trigger_for

load_dotenv()

LATE_MINUTES = 50  # Bayshore starters/alternators arrive this late (planted pattern)


def log(msg: str) -> None:
    print(f"[sim] {msg}", file=sys.stderr, flush=True)


def get_agent() -> tuple[Callable[..., Any], bool]:
    """(run_day, is_stub). brain's agent.sal.run_day if importable, else the scripted stub."""
    if os.getenv("SIM_STUB_AGENT") != "1":
        try:
            from agent.sal import run_day  # type: ignore

            return run_day, False
        except Exception as e:  # noqa: BLE001
            log(f"agent.sal unavailable ({e.__class__.__name__}: {e}); using stub agent")
    from sim.stub_agent import run_day

    return run_day, True


def _as_dict(result: Any) -> dict:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    for attr in ("model_dump", "dict", "_asdict"):
        f = getattr(result, attr, None)
        if callable(f):
            try:
                return dict(f())
            except Exception:
                pass
    return dict(getattr(result, "__dict__", {}))


def _day_events(run_id: str, day: str) -> list[dict]:
    return [ev for ev in read_log(run_id) if ev.get("day") == day]


def _sync_clock(clock: SimClock, events: list[dict]) -> None:
    for ev in events:
        try:
            clock.advance_to(datetime.fromisoformat(ev["ts"]))
        except Exception:
            continue


def _set_ctx_env(run_id: str, day: str, clock: SimClock, variant: flags.Variant) -> None:
    os.environ["SAL_RUN_ID"] = run_id
    os.environ["SAL_DAY"] = day
    os.environ["SAL_SIM_TS"] = clock.iso()
    variant.export_env()


def deliver_orders(e: Emitter, events: list[dict]) -> list[dict]:
    """Advance the clock to each counter order's ETA and emit order.delivered (actor vendor)."""
    delivered_ids = {(ev.get("refs") or {}).get("order_id") for ev in events if ev["type"] == "order.delivered"}
    out = []
    pending = []
    for ev in events:
        if ev.get("type") != "order.placed":
            continue
        refs, data = ev.get("refs") or {}, ev.get("data") or {}
        oid = refs.get("order_id")
        if oid in delivered_ids or data.get("channel") == "shopify":
            continue
        try:
            eta = datetime.fromisoformat(data["eta"]) if data.get("eta") else None
        except Exception:
            eta = None
        placed = datetime.fromisoformat(ev["ts"])
        eta = eta or placed + timedelta(minutes=60)
        vendor = refs.get("vendor_id", "")
        part_type = str(data.get("part_type", "")).lower()
        late = vendor == "bayshore" and part_type in metrics.ROUTED_PART_TYPES
        arrived = eta + timedelta(minutes=LATE_MINUTES if late else 0)
        pending.append((arrived, eta, ev, late))
    for arrived, eta, ev, late in sorted(pending, key=lambda x: x[0]):
        e.clock.advance_to(arrived)
        refs = ev.get("refs") or {}
        vendor = refs.get("vendor_id", "vendor")
        msg = f"{vendor.title()} van delivered {refs.get('order_id', 'order')}"
        msg += f" ({LATE_MINUTES} min late)" if late else " on time"
        out.append(e("order.delivered", "vendor", msg, sources=[{"name": "Vendor", "ref": refs.get("order_id", "")}],
                     refs={k: v for k, v in refs.items() if k in ("ro_id", "order_id", "vendor_id")},
                     data={"on_time": not late, "eta": eta.isoformat(), "arrived": arrived.isoformat()}))
    return out


def approve_rule(e: Emitter, rule_id: str, run_id: str) -> dict:
    """Owner approves Sal's proposal. Uses tools' approve_rule when present (auto-emits rule.approved +
    gate.enabled); otherwise the sim emits them. Always flips the Statsig gate (console API or override)."""
    before = {ev["id"] for ev in read_log(run_id)}
    res: dict = {}
    try:
        from tools.server import approve_rule as tools_approve  # type: ignore

        fn = getattr(tools_approve, "fn", tools_approve)
        r = fn(rule_id=rule_id)
        if hasattr(r, "__await__"):
            import asyncio

            r = asyncio.run(r)  # type: ignore[arg-type]
        res = r if isinstance(r, dict) else {}
    except Exception as ex:  # noqa: BLE001
        log(f"tools approve_rule unavailable ({ex.__class__.__name__}); sim emits rule.approved")
    gate = flags.enable_gate()
    new_types = {ev["type"] for ev in read_log(run_id) if ev["id"] not in before}
    if "rule.approved" not in new_types:
        e("rule.approved", "owner", "Owner approved: route starters & alternators to Mission", advance_min=3,
          sources=[{"name": "Senso", "ref": str(res.get("senso_content_id") or "rules")}],
          refs={"rule_id": rule_id}, data={"approved_by": "owner"})
    if "gate.enabled" not in new_types:
        e("gate.enabled", "system", f"Statsig gate {flags.GATE} is ON", advance_min=0.5,
          sources=[{"name": "Statsig", "ref": flags.GATE}], refs={"rule_id": rule_id},
          data={"gate": flags.GATE, "method": gate.get("method")})
    return {**res, "gate": gate}


def emit_metrics(e: Emitter, run_id: str, day: str, m_list: list[metrics.Metrics], label: str) -> None:
    where = metrics.store(run_id, day, m_list)
    if len(m_list) == 2:
        off, on = m_list
        summary = (f"Starter jobs gate OFF vs ON: on-time {off.on_time_pct:.0f}% -> {on.on_time_pct:.0f}%, "
                   f"late cost ${off.expected_late_penalty:.0f} -> ${on.expected_late_penalty:.0f}")
        saved = round(off.expected_late_penalty - on.expected_late_penalty
                      - (on.avg_cost - off.avg_cost) * on.jobs, 2)
        money = {"saved": saved}
    else:
        m = m_list[0]
        summary = (f"{label}: {m.jobs} orders, on-time {m.on_time_pct:.0f}%, {m.escalations:.0f} escalations, "
                   f"avg ${m.avg_cost:.0f}")
        money = None
    e("metrics.updated", "system", summary, sources=[{"name": "Statsig", "ref": flags.GATE}],
      money=money, data={"label": label, "store": where, "variants": [m.as_dict() for m in m_list]})


def run_day(day: str, run_id: str, cli_variant: str | None = None, trigger_text: str | None = None) -> dict:
    t0 = time.time()
    variant = flags.resolve(cli_variant)
    clock = SimClock(day)
    e = Emitter(run_id, clock)
    trigger = trigger_for(day)
    if trigger_text:  # e.g. a Firedrill drill's opening message
        trigger["text"] = trigger_text
    _set_ctx_env(run_id, day, clock, variant)
    log(f"{day.upper()} {clock.iso()} run={run_id} variant={variant.name} ({variant.source}) strategy={variant.strategy}")

    agent_fn, is_stub = get_agent()
    if trigger["kind"] == "tech_message" and is_stub:  # real Sal emits repair_order.created (actor tech) itself
        e("repair_order.created", "tech", trigger["text"][:140], sources=[{"name": "Shop", "ref": "bay-tablet"}],
          refs={"ro_id": trigger["ro_id"]}, data={"trigger": trigger, "bay": trigger.get("bay")})
        clock.advance(minutes=1)

    os.environ["SAL_SIM_TS"] = clock.iso()
    result: dict = {}
    try:
        result = _as_dict(agent_fn(day=day, trigger=trigger, variant=variant.arm, run_id=run_id,
                                   sim_ts=clock.iso()))
    except Exception as ex:  # noqa: BLE001
        traceback.print_exc()
        e("error", "system", f"Sal run failed on {day}: {ex.__class__.__name__}"[:140],
          reason=str(ex)[:280], data={"stage": "agent"})
    events = _day_events(run_id, day)
    _sync_clock(clock, events)
    if result.get("end_ts"):
        try:
            clock.advance_to(datetime.fromisoformat(result["end_ts"]))
        except Exception:
            pass

    deliver_orders(e, events)

    if day == "sun":
        rule_ids = [(ev.get("refs") or {}).get("rule_id") for ev in events if ev["type"] == "rule.proposed"]
        rule_id = next((r for r in reversed(rule_ids) if r), None) or result.get("rule_id")
        if rule_id:
            ACTORS.request("rule", rule_id, actor="owner", summary="Route starters & alternators to Mission")
            status = ACTORS.wait("rule", rule_id)
            log(f"owner {status} rule {rule_id}")
            if status == "approved":
                clock.advance(minutes=2)
                approve_rule(e, rule_id, run_id)
                late, price = metrics.vendor_stats_from_events(_day_events(run_id, day))
                emit_metrics(e, run_id, day, [metrics.replay_starter(False, late, price),
                                              metrics.replay_starter(True, late, price)], "starter replay")
        else:
            log("no rule.proposed on SUN; skipping approval + replay")

    day_events = _day_events(run_id, day)
    if not any(ev["type"] == "sal.summary" for ev in day_events):
        e("sal.summary", "sal", _fallback_summary(day, day_events), advance_min=1,
          data={"stub": is_stub, "generated_by": "sim"})
        day_events = _day_events(run_id, day)
    if day != "sun":
        emit_metrics(e, run_id, day, [metrics.run_metrics(day_events, variant.name)], f"{day.upper()} run")
    dt = time.time() - t0
    log(f"{day.upper()} done in {dt:.1f}s; {len(_day_events(run_id, day))} events")
    return {"day": day, "run_id": run_id, "variant": variant.as_dict(), "seconds": round(dt, 1),
            "stub_agent": is_stub, "result": {k: v for k, v in result.items() if k in ("ok", "orders", "rule_id")}}


def _fallback_summary(day: str, events: list[dict]) -> str:
    n = {t: sum(1 for ev in events if ev["type"] == t) for t in ("order.placed", "escalation", "part.rejected")}
    return (f"{day.upper()} wrap: {n['order.placed']} orders, {n['part.rejected']} rejections, "
            f"{n['escalation']} escalations. Trace is in the timeline.")


def run_week(run_id: str, cli_variant: str | None = None, keep_gate: bool = False) -> list[dict]:
    if not keep_gate:
        flags.clear_override()  # the week starts before the owner approved the routing rule
    return [run_day(d, run_id, cli_variant) for d in WEEK_ORDER]


def default_run_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%m%d-%H%M%S')}"


def start_api_thread(port: int = 8102) -> None:
    import threading

    import uvicorn

    from sim.api import app

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    threading.Thread(target=uvicorn.Server(cfg).run, daemon=True).start()
    log(f"interactive: approvals via POST http://127.0.0.1:{port}/sim/approve")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sim.run", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--day", choices=WEEK_ORDER)
    g.add_argument("--week", action="store_true")
    ap.add_argument("--variant", choices=("on", "off"), help="force gate sal_vendor_routing_v2")
    ap.add_argument("--run-id")
    ap.add_argument("--interactive", action="store_true", help="wait for UI approve buttons")
    ap.add_argument("--keep-gate", action="store_true", help="--week: keep a previously approved gate override")
    ap.add_argument("--stub", action="store_true", help="force the scripted stub agent")
    a = ap.parse_args(argv)
    if a.stub:
        os.environ["SIM_STUB_AGENT"] = "1"
    configure(interactive=a.interactive)
    if a.interactive:
        start_api_thread()
    run_id = a.run_id or default_run_id("week" if a.week else a.day)
    if a.run_id:  # a named run (e.g. demo) is re-recorded from scratch
        from sim.emit import log_path

        for p in (log_path(run_id), log_path(run_id).with_name("metrics.json")):
            if p.exists():
                p.unlink()
    t0 = time.time()
    results = run_week(run_id, a.variant, a.keep_gate) if a.week else [run_day(a.day, run_id, a.variant)]
    from sim.emit import log_path, validate

    evs = read_log(run_id)
    bad = sum(1 for ev in evs if validate(ev))
    log(f"run {run_id}: {len(evs)} events, {bad} invalid, {time.time() - t0:.1f}s -> {log_path(run_id)}")
    for r in results:
        log(f"  {r['day']}: {r['seconds']}s variant={r['variant']['name']} stub={r['stub_agent']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
