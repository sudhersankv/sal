"""Sal's day runner: Claude Agent SDK loop over the sal-tools MCP server (SPEC §4, T3 B1-B5).

    python -m agent.sal --day mon|tue|wed|fri|sun [--variant on|off] [--run-id X]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agent import analytics

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = Path(__file__).with_name("prompts") / "sal.md"
SERVER_NAME = "sal-tools"
TOOL_PREFIX = f"mcp__{SERVER_NAME}__"
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_TURNS = 40

# Simulated week Mon Nov 16 - Sun Nov 22, 2026 (contracts/demo_script.md).
DEFAULT_SIM_TS = {
    "mon": "2026-11-16T09:12:00-08:00",
    "tue": "2026-11-17T10:05:00-08:00",
    "wed": "2026-11-18T07:30:00-08:00",
    "thu": "2026-11-19T09:00:00-08:00",
    "fri": "2026-11-20T16:00:00-08:00",
    "sat": "2026-11-21T09:00:00-08:00",
    "sun": "2026-11-22T18:00:00-08:00",
}

# Used only when the sim does not pass a trigger (CLI / tests). The sim owns real triggers.
DEFAULT_TRIGGERS: dict[str, dict | None] = {
    "mon": {
        "actor": "tech",
        "channel": "counter",
        "text": "Civic in bay 2, P0141, VIN 19XFB2F58EE200123, customer promised by 3 PM. RO-1042, customer CUST-311.",
    },
    "tue": {
        "actor": "tech",
        "channel": "counter",
        "text": "F-150 in bay 4, no-charge, alternator is dead. VIN 1FTFW1ET5DFC10312. RO-1047, customer CUST-188, "
                "promised by 5 PM.",
    },
    "wed": None,
    "fri": {
        "actor": "system",
        "channel": "inbox",
        "text": "Bayshore Auto Parts emailed their November statement.",
        "path": "seed/statements/bayshore_nov.pdf",
        "vendor_id": "bayshore",
    },
    "sun": None,
}

DAY_GOALS = {
    "mon": "Urgent buy for the car on the lift (procedure MON).",
    "tue": "Urgent buy that may exceed the spend cap (procedure TUE).",
    "wed": "No trigger. Proactive restock before the week's bookings run you dry (procedure WED).",
    "fri": "Reconcile the vendor statement (procedure FRI).",
    "sun": "Weekly vendor review. Get smarter (procedure SUN).",
}


@dataclass
class RunResult:
    run_id: str
    day: str
    variant: str
    ok: bool = False
    summary: str = ""
    num_turns: int = 0
    cost_usd: float | None = None
    duration_ms: int = 0
    tool_calls: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    escalations: int = 0
    emitted_types: list[str] = field(default_factory=list)  # types Sal sent via emit_event
    summary_emitted_by: str = ""  # "sal" | "runner"
    orders: list[str] = field(default_factory=list)  # order ids placed (counter or Shopify)
    rule_id: str | None = None  # from propose_rule (SUN)
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


# ---------------------------------------------------------------- prompt / config


GATE = "sal_vendor_routing_v2"


def normalize_variant(variant: str | dict | None) -> tuple[str, dict[str, str]]:
    """Sim passes a Statsig variant dict ({name, sal_vendor_routing_v2, sal_policy:{strategy}}) or a name.

    Returns (name, extra tool env)."""
    if not isinstance(variant, dict):
        name = str(variant or os.getenv("SAL_VARIANT") or "off")
        return name, {k: os.environ[k] for k in ("SAL_GATE_ROUTING_V2", "SAL_POLICY_STRATEGY") if os.getenv(k)}
    name = str(variant.get("name") or variant.get("variant") or "off")
    env: dict[str, str] = {}
    gate = variant.get(GATE, variant.get("gate_routing_v2"))
    if gate is not None:
        env["SAL_GATE_ROUTING_V2"] = "1" if gate else "0"
    cfg = variant.get("sal_policy")
    strategy = (cfg.get("strategy") if isinstance(cfg, dict) else None) or variant.get("strategy")
    if strategy:
        env["SAL_POLICY_STRATEGY"] = str(strategy)
    return name, env


def build_system_prompt(day: str, run_id: str, sim_ts: str, variant: str,
                        extra: dict[str, str] | None = None) -> str:
    base = PROMPT_PATH.read_text(encoding="utf-8")
    extra = extra or {}
    gate_on = extra.get("SAL_GATE_ROUTING_V2") == "1"
    ctx = (
        "\n\n## Run context (set by the sim; do not change)\n"
        f"- day: {day}\n- run_id: {run_id}\n- shop time now: {sim_ts}\n"
        f"- policy variant (Statsig arm, chosen by sim): {variant}\n"
        f"- routing gate {GATE}: {'ON' if gate_on else 'OFF'}\n"
        f"- sal_policy.strategy: {extra.get('SAL_POLICY_STRATEGY', 'rules_aware')}\n"
        f"- spend cap: ${os.getenv('SPEND_CAP', '200')}\n"
        "- user_id: shop-001 (Mission Street Auto)\n"
    )
    return base + ctx


def build_user_prompt(day: str, trigger: dict | None, sim_ts: str) -> str:
    head = f"{day.upper()} {sim_ts}. {DAY_GOALS.get(day, '')}"
    if not trigger:
        return head + "\nNo one asked. Run the procedure for today."
    return head + "\nTrigger:\n" + json.dumps(trigger, indent=2)


def tool_env(day: str, run_id: str, sim_ts: str, variant: str,
             extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        **(extra or {}),
        "SAL_RUN_ID": run_id,
        "SAL_DAY": day,
        "SAL_SIM_TS": sim_ts,
        "SAL_VARIANT": variant,
        "PYTHONPATH": str(ROOT),
        "PYTHONIOENCODING": "utf-8",
    }
    # pass through non-secret runtime knobs the tools read; secrets are loaded by tools from .env
    for k in ("SPEND_CAP", "DEMO_MODE", "DB_BACKEND", "SAL_EVENTS_URL"):
        if os.getenv(k):
            env[k] = os.environ[k]
    return env


def tools_module() -> str:
    """sal-tools entry module; override with SAL_TOOLS_MODULE (e.g. tests.e2e.fake_tools)."""
    return os.getenv("SAL_TOOLS_MODULE") or "tools.server"


def mcp_server_config(env: dict[str, str]) -> dict[str, Any]:
    return {
        SERVER_NAME: {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", tools_module()],
            "env": env,
        }
    }


def build_options(day: str, run_id: str, sim_ts: str, variant: str | dict, max_turns: int | None = None):
    from claude_agent_sdk import ClaudeAgentOptions

    name, extra = normalize_variant(variant)
    env = tool_env(day, run_id, sim_ts, name, extra)
    return ClaudeAgentOptions(
        system_prompt=build_system_prompt(day, run_id, sim_ts, name, extra),
        model=os.getenv("SAL_MODEL") or DEFAULT_MODEL,
        tools=[],  # no built-in Claude Code tools (no Bash, no filesystem)
        mcp_servers=mcp_server_config(env),
        strict_mcp_config=True,
        allowed_tools=[f"{TOOL_PREFIX}*"],
        disallowed_tools=[f"{TOOL_PREFIX}approve_rule"],
        permission_mode="bypassPermissions",
        setting_sources=[],  # ignore user/project Claude Code settings, CLAUDE.md, hooks
        max_turns=max_turns or int(os.getenv("SAL_MAX_TURNS", DEFAULT_MAX_TURNS)),
        cwd=str(ROOT),
        env=env,
    )


# ---------------------------------------------------------------- helpers


def short_tool(name: str) -> str:
    return name[len(TOOL_PREFIX):] if name.startswith(TOOL_PREFIX) else name


def parse_tool_result(content: Any) -> Any:
    """MCP tool results arrive as str or [{type:text,text:...}]; return parsed JSON if possible."""
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        content = "\n".join(texts)
    if isinstance(content, str):
        try:
            return json.loads(content)
        except (ValueError, TypeError):
            return content
    return content


def result_flags(parsed: Any, is_error: bool | None) -> tuple[bool, bool]:
    """(is_error, is_escalation) for a tool result."""
    err = bool(is_error) or (isinstance(parsed, dict) and "error" in parsed)
    esc = isinstance(parsed, dict) and "escalation" in parsed
    return err, esc


def fallback_summary_event(day: str, run_id: str, sim_ts: str, variant: str, text: str, res: RunResult) -> dict:
    line = " ".join((text or "").split()) or f"{day.upper()} run finished; {len(res.tool_calls)} tool calls."
    if res.error:
        line = f"{day.upper()} run cut short: {res.error}"
    return {
        "run_id": run_id,
        "ts": sim_ts,
        "day": day,
        "type": "sal.summary",
        "actor": "sal",
        "summary": line[:140],
        "reason": line[:280],
        "data": {
            "emitted_by": "runner",
            "variant": variant,
            "tool_calls": len(res.tool_calls),
            "escalations": res.escalations,
            "tool_errors": len(res.tool_errors),
        },
    }


async def emit_via_tools(event: dict, env: dict[str, str]) -> bool:
    """Call sal-tools emit_event over a short-lived stdio session (same path Sal's own events take)."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=sys.executable, args=["-m", tools_module()], env={**os.environ, **env}, cwd=str(ROOT)
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                out = await asyncio.wait_for(session.call_tool("emit_event", event), timeout=30)
                return not getattr(out, "isError", False)
    except Exception as e:  # noqa: BLE001 - fallback path must never raise
        print(f"[sal] emit_via_tools failed: {type(e).__name__}: {e}", file=sys.stderr)
        return False


def emit_direct(event: dict) -> bool:
    """Last resort: POST to ui/server and append to runs/<run_id>/events.jsonl."""
    ev = {"id": "evt_" + uuid.uuid4().hex[:12], **event}
    ok = False
    try:
        import httpx

        url = os.getenv("SAL_EVENTS_URL", "http://localhost:8100/events")
        ok = httpx.post(url, json=ev, timeout=3).status_code < 300
    except Exception:  # noqa: BLE001
        pass
    if not ok:
        p = ROOT / "runs" / event["run_id"] / "events.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev) + "\n")
        ok = True
    return ok


# ---------------------------------------------------------------- main loop


async def run_day_async(
    day: str,
    trigger: dict | None = None,
    variant: str | dict = "off",
    run_id: str | None = None,
    sim_ts: str | None = None,
    max_turns: int | None = None,
) -> RunResult:
    from claude_agent_sdk import (
        AssistantMessage,
        ResultMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        query,
    )

    if day not in DAYS:
        raise ValueError(f"day must be one of {DAYS}")
    load_env()
    run_id = run_id or f"{day}-{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"
    sim_ts = sim_ts or DEFAULT_SIM_TS[day]
    options = build_options(day, run_id, sim_ts, variant, max_turns)
    variant, extra_env = normalize_variant(variant)
    res = RunResult(run_id=run_id, day=day, variant=variant)
    prompt = build_user_prompt(day, trigger, sim_ts)
    model = options.model or DEFAULT_MODEL

    tracker = analytics.SessionTracker(run_id=run_id, day=day, variant=variant, model=model)
    tracker.user_message(prompt)
    pending: dict[str, tuple[str, dict, float]] = {}  # tool_use_id -> (name, input, t0)
    last_text = ""
    t_turn = time.monotonic()
    t0 = time.monotonic()
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                texts = [b.text for b in msg.content if isinstance(b, TextBlock) and b.text.strip()]
                uses = [b for b in msg.content if isinstance(b, ToolUseBlock)]
                now = time.monotonic()
                if texts:
                    last_text = "\n".join(texts)
                    print(f"[sal] {last_text}", flush=True)
                tracker.ai_message("\n".join(texts), [short_tool(u.name) for u in uses],
                                   (now - t_turn) * 1000, msg.usage, msg.model or model, msg.stop_reason)
                t_turn = now
                for u in uses:
                    name = short_tool(u.name)
                    res.tool_calls.append(name)
                    pending[u.id] = (name, u.input or {}, now)
                    print(f"[sal] -> {name} {json.dumps(u.input)[:200]}", flush=True)
                    if name == "emit_event" and isinstance(u.input, dict):
                        res.emitted_types.append(str(u.input.get("type")))
            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for b in msg.content:
                    if not isinstance(b, ToolResultBlock):
                        continue
                    name, inp, ts = pending.pop(b.tool_use_id, ("?", {}, time.monotonic()))
                    parsed = parse_tool_result(b.content)
                    err, esc = result_flags(parsed, b.is_error)
                    if err:
                        res.tool_errors.append(name)
                        print(f"[sal] !! {name} error: {str(parsed)[:200]}", flush=True)
                    if esc:
                        res.escalations += 1
                    elif not err and isinstance(parsed, dict):
                        oid = parsed.get("order_id") or parsed.get("shopify_order_id")
                        if name.startswith("place_") and oid:
                            res.orders.append(str(oid))
                        if name == "propose_rule" and parsed.get("rule_id"):
                            res.rule_id = str(parsed["rule_id"])
                    tracker.tool_call(name, inp, parsed, (time.monotonic() - ts) * 1000, not err)
                    if esc:
                        tracker.custom("sal_escalation", {"tool": name})
                    elif name.startswith("place_") and not err:
                        tracker.custom("sal_order_placed", {"tool": name})
                    elif name == "propose_rule" and not err:
                        tracker.custom("sal_rule_proposed", {})
                t_turn = time.monotonic()
            elif isinstance(msg, ResultMessage):
                res.num_turns = msg.num_turns
                res.cost_usd = msg.total_cost_usd
                res.duration_ms = msg.duration_ms
                res.ok = not msg.is_error
                if msg.is_error:
                    res.error = f"{msg.subtype}: {'; '.join(msg.errors or []) or msg.terminal_reason or ''}"
                if msg.result:
                    last_text = msg.result
                tracker.run_cost(msg.total_cost_usd, msg.usage, msg.duration_ms, model)
    except Exception as e:  # noqa: BLE001 - B5: a crashed loop still produces a summary
        res.ok = False
        res.error = f"{type(e).__name__}: {e}"
        print(f"[sal] run failed: {res.error}", file=sys.stderr)
    finally:
        res.duration_ms = res.duration_ms or int((time.monotonic() - t0) * 1000)
        res.summary = last_text.strip()
        if "sal.summary" in res.emitted_types:
            res.summary_emitted_by = "sal"
        else:
            ev = fallback_summary_event(day, run_id, sim_ts, variant, res.summary, res)
            env = tool_env(day, run_id, sim_ts, variant, extra_env)
            if await emit_via_tools(ev, env) or emit_direct(ev):
                res.summary_emitted_by = "runner"
        tracker.end(res)
    return res


def run_day(
    day: str,
    trigger: dict | None = None,
    variant: str | dict = "off",
    run_id: str | None = None,
    sim_ts: str | None = None,
    max_turns: int | None = None,
) -> RunResult:
    """Sync entry point for sim/: run one Sal day and return the result."""
    return asyncio.run(run_day_async(day, trigger, variant, run_id, sim_ts, max_turns))


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agent.sal")
    ap.add_argument("--day", required=True, choices=DAYS)
    ap.add_argument("--variant", default="off", help="Statsig arm from the sim (on|off|...)")
    ap.add_argument("--run-id")
    ap.add_argument("--sim-ts")
    ap.add_argument("--trigger", help="JSON trigger payload (default: built-in demo trigger)")
    ap.add_argument("--max-turns", type=int)
    a = ap.parse_args(argv)
    load_env()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    trigger = json.loads(a.trigger) if a.trigger else DEFAULT_TRIGGERS.get(a.day)
    res = run_day(a.day, trigger, a.variant, a.run_id, a.sim_ts, a.max_turns)
    print(res.to_json())
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
