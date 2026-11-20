"""Sal chat mode (D-010): free-form staff conversation -> Sal picks the intent and uses sal-tools.

`run_chat(chat_id, text, history=None) -> ChatReply`. Conversation memory: runs/chat/<chat_id>.jsonl (last
~20 turns). Emits `chat.message` for every inbound/outbound message and `action.status` for each thing Sal
starts (contracts/tools.md, Additions 14:10). run_id = chat-<chat_id>-<yyyymmdd>; never shown to the user.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent import analytics
from agent import sal as core

CHAT_PROMPT = Path(__file__).with_name("prompts") / "sal_chat.md"
HISTORY_TURNS = 20
PT = timezone(timedelta(hours=-8))
NEEDS_OWNER = re.compile(r"^\s*NEEDS_OWNER:\s*(.+?)\s*$", re.M)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass
class ChatReply:
    text: str
    run_id: str
    needs_owner: str | None = None  # short title of the decision the owner must make
    actions: list[dict] = field(default_factory=list)  # final action.status per action
    orders: list[dict] = field(default_factory=list)  # {order_id, total, eta, vendor}
    tool_calls: list[str] = field(default_factory=list)
    why: list[str] = field(default_factory=list)  # short reasons + sources behind this turn's decisions
    persona_url: str | None = None  # owner verification link (over-cap)
    cost_usd: float | None = None
    error: str | None = None


# ---------------------------------------------------------------- memory


def chat_dir() -> Path:
    return core.ROOT / "runs" / "chat"


def chat_run_id(chat_id: Any, now: datetime) -> str:
    return f"chat-{chat_id}-{now:%Y%m%d}"


def load_history(chat_id: Any, n: int = HISTORY_TURNS) -> list[dict]:
    p = chat_dir() / f"{chat_id}.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows[-n:]


def append_history(chat_id: Any, role: str, text: str, notes: str | None = None,
                   why: list[str] | None = None) -> None:
    p = chat_dir() / f"{chat_id}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(PT).isoformat(timespec="seconds"), "role": role, "text": text}
    if notes:
        row["notes"] = notes
    if why:
        row["why"] = why
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def render_prompt(history: list[dict], text: str, now: datetime) -> str:
    lines = [f"Now: {now:%a %b %d %Y, %I:%M %p} PT. Spend cap ${os.getenv('SPEND_CAP', '200')}.", ""]
    if history:
        lines.append("Chat so far (oldest first):")
        for h in history:
            who = "Sal" if h.get("role") == "sal" else "Them"
            lines.append(f"{who}: {h.get('text', '')}")
            if h.get("notes"):
                lines.append(f"[Sal did: {h['notes']}]")
        lines.append("")
    lines.append(f"New message: {text}")
    return "\n".join(lines)


def clean_text(s: str) -> str:
    """Telegram gets plain text: drop markdown emphasis/headers the model sometimes adds."""
    s = s.replace("**", "").replace("__", "")
    lines = [ln.lstrip("#").lstrip() if ln.lstrip().startswith("#") else ln for ln in s.splitlines()]
    return chr(10).join(lines)


def why_line(reason: str, sources: list | None) -> str:
    names = []
    for src in sources or []:
        if isinstance(src, dict) and src.get("name"):
            names.append(src["name"] + (f" {src['ref']}" if src.get("ref") else ""))
    return " ".join(str(reason).split())[:200] + (f" (sources: {', '.join(names[:3])})" if names else "")


def last_why(chat_id: Any) -> list[str]:
    for row in reversed(load_history(chat_id, 200)):
        if row.get("why"):
            return row["why"]
    return []


def waiting_items(chat_id: Any) -> list[dict]:
    """Latest action.status per action across this chat's logs that is still waiting on the owner."""
    return [a for a in action_index(chat_id).values() if a.get("status") == "waiting_owner"]


def action_index(chat_id: Any = "*") -> dict[str, dict]:
    """action_id -> latest action.status data (+ chat_id, refs, ts) across chat logs. chat_id "*" = every chat."""
    latest: dict[str, dict] = {}
    for p in sorted((core.ROOT / "runs").glob(f"chat-{chat_id}-*/events.jsonl")):
        cid = p.parent.name[len("chat-"):-len("-yyyymmdd")]
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "action.status" and (ev.get("data") or {}).get("action_id"):
                latest[ev["data"]["action_id"]] = {**ev["data"], "chat_id": cid, "refs": ev.get("refs") or {},
                                                   "ts": ev.get("ts"), "run_id": ev.get("run_id")}
    return latest


def split_needs_owner(reply: str) -> tuple[str, str | None]:
    m = NEEDS_OWNER.search(reply or "")
    if not m:
        return (reply or "").strip(), None
    return NEEDS_OWNER.sub("", reply).strip(), m.group(1)[:120]


# ---------------------------------------------------------------- events


class Emitter:
    def __init__(self, run_id: str, day: str, chat_id: Any, channel: str):
        self.run_id, self.day, self.chat_id, self.channel = run_id, day, chat_id, channel

    def __call__(self, type: str, actor: str, summary: str, **extra: Any) -> None:
        try:
            from sim.emit import build, emit

            ts = datetime.now(PT).isoformat(timespec="seconds")
            emit(build(self.run_id, self.day, ts, type, actor, (summary or type)[:140], **extra))
        except Exception as e:  # noqa: BLE001 - logging must never break the chat
            print(f"[sal.chat] emit {type} failed: {type(e).__name__}: {e}", file=sys.stderr)

    def message(self, actor: str, text: str, intent: str | None = None) -> None:
        data = {"channel": self.channel, "chat_id": str(self.chat_id), "text": text[:4000]}
        if intent:
            data["intent"] = intent
        self("chat.message", actor, " ".join(text.split())[:140] or "(empty)", data=data)


class Actions:
    """Maps Sal's tool calls to action.status lifecycle events (planned → waiting_owner → in_progress → done/refused)."""

    def __init__(self, emit: Emitter):
        self.emit = emit
        self.by_use: dict[str, str] = {}  # tool_use_id -> action_id
        self.state: dict[str, dict] = {}  # action_id -> last status payload

    def set(self, action_id: str, kind: str, status: str, title: str, refs: dict | None = None) -> None:
        data = {"action_id": action_id, "kind": kind, "status": status, "title": title[:120]}
        refs = {k: str(v) for k, v in (refs or {}).items() if v}
        self.state[action_id] = {**data, "refs": refs}
        self.emit("action.status", "sal", f"{title} — {status.replace('_', ' ')}"[:140], data=data,
                  refs=refs or None)

    def on_use(self, use_id: str, name: str, inp: dict) -> None:
        aid = "act_" + uuid.uuid4().hex[:10]
        if name == "place_counter_order":
            self.by_use[use_id] = aid
            self.set(aid, "order", "in_progress", f"Ordering {inp.get('sku', 'part')} from {inp.get('vendor_id', '?')}",
                     {"ro_id": inp.get("ro_id"), "approval_id": inp.get("approval_id")})
        elif name == "place_shopify_order":
            self.by_use[use_id] = aid
            n = len(inp.get("lines") or [])
            self.set(aid, "restock", "in_progress", f"Restock order, {n} lines (online)",
                     {"approval_id": inp.get("approval_id")})
        elif name == "request_owner_approval":
            self.by_use[use_id] = aid
            self.set(aid, "quote", "waiting_owner", f"Quote ${inp.get('total', '?')} to car owner",
                     {"ro_id": inp.get("ro_id")})
        elif name == "verify_owner":
            self.by_use[use_id] = aid
            self.set(aid, "verification", "waiting_owner", f"Owner ID check for ${inp.get('order_total', '?')} order",
                     {"ro_id": inp.get("ro_id")})

    def on_result(self, use_id: str, name: str, parsed: Any, err: bool, esc: bool) -> dict | None:
        """Returns an order dict when an order was placed."""
        p = parsed if isinstance(parsed, dict) else {}
        aid = self.by_use.pop(use_id, None)
        if name == "plan_restock" and not err:
            lines = p.get("lines") or []
            if lines:
                self.set("act_" + uuid.uuid4().hex[:10], "restock", "planned",
                         f"Restock plan: {len(lines)} items short")
            return None
        if name == "reconcile_statement" and not err and p.get("missing_core_credits"):
            self.set("act_" + uuid.uuid4().hex[:10], "dispute", "waiting_owner",
                     f"Dispute drafted: ${p.get('total_due', '?')} missing core credits")
            return None
        if name == "propose_rule" and not err:
            self.set("act_" + uuid.uuid4().hex[:10], "rule", "waiting_owner", "Rule proposed, needs owner",
                     {"rule_id": p.get("rule_id")})
            return None
        if not aid:
            return None
        prev = self.state[aid]
        kind, title, refs = prev["kind"], prev["title"], dict(prev["refs"])
        if err:
            self.set(aid, kind, "failed", title, refs)
        elif esc:
            self.set(aid, kind, "refused", title, refs)
        elif name.startswith("place_"):
            oid = p.get("order_id") or p.get("shopify_order_id")
            refs["order_id"] = oid
            self.set(aid, kind, "done", title, refs)
            return {"order_id": oid, "total": p.get("total"), "eta": p.get("eta"), "kind": kind}
        else:
            status = p.get("status")
            refs["approval_id"] = p.get("approval_id") or p.get("inquiry_id")
            self.set(aid, kind, {"approved": "done", "declined": "refused"}.get(status, "waiting_owner"), title, refs)
        return None


# ---------------------------------------------------------------- the turn


def _notes(name: str, parsed: Any) -> str | None:
    """Compact memory of what a tool returned, so the next turn can act on it."""
    if not isinstance(parsed, dict):
        return None
    if name == "plan_restock":
        lines = [f"{x.get('sku')}x{x.get('order_qty')}" for x in parsed.get("lines") or []]
        return f"plan_restock: {', '.join(lines)}; {json.dumps(parsed.get('vendor_suggestion'), default=str)[:200]}"
    if name.startswith("place_") or name in ("compute_quote", "verify_owner", "request_owner_approval"):
        return f"{name}: {json.dumps(parsed, default=str)[:300]}"
    if name == "get_inventory":
        low = [f"{i.get('sku')}={i.get('qty')}" for i in parsed.get("items") or [] if i.get("qty", 0) <= i.get("min_qty", 0)]
        return f"low stock: {', '.join(low)[:300]}" if low else None
    return None


async def run_chat_async(chat_id: Any, text: str, history: list[dict] | None = None, *,
                         actor: str = "owner", channel: str = "telegram", max_turns: int | None = None) -> ChatReply:
    from claude_agent_sdk import (
        AssistantMessage,
        ResultMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
        query,
    )

    core.load_env()
    now = datetime.now(PT)
    day = WEEKDAYS[now.weekday()]
    run_id = chat_run_id(chat_id, now)
    sim_ts = now.isoformat(timespec="seconds")
    history = load_history(chat_id) if history is None else history
    emit = Emitter(run_id, day, chat_id, channel)
    actions = Actions(emit)
    reply = ChatReply(text="", run_id=run_id)

    emit.message(actor, text)
    append_history(chat_id, "user", text)

    options = core.build_options(day, run_id, sim_ts, os.getenv("SAL_VARIANT", "off"), max_turns or 30)
    options.system_prompt = CHAT_PROMPT.read_text(encoding="utf-8")
    prompt = render_prompt(history, text, now)
    tracker = analytics.SessionTracker(run_id=run_id, day=day, variant=os.getenv("SAL_VARIANT", "off"),
                                       model=options.model or core.DEFAULT_MODEL)
    tracker.user_message(text)
    pending: dict[str, tuple[str, dict, float]] = {}
    notes: list[str] = []
    why: list[str] = []
    last_text, escalations = "", []
    t_turn = time.monotonic()
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                texts = [b.text for b in msg.content if isinstance(b, TextBlock) and b.text.strip()]
                uses = [b for b in msg.content if isinstance(b, ToolUseBlock)]
                if texts:
                    last_text = "\n".join(texts)
                tracker.ai_message("\n".join(texts), [core.short_tool(u.name) for u in uses],
                                   (time.monotonic() - t_turn) * 1000, msg.usage, msg.model or "", msg.stop_reason)
                for u in uses:
                    name = core.short_tool(u.name)
                    reply.tool_calls.append(name)
                    pending[u.id] = (name, u.input or {}, time.monotonic())
                    actions.on_use(u.id, name, u.input or {})
                    print(f"[sal.chat] -> {name} {json.dumps(u.input)[:160]}", file=sys.stderr, flush=True)
                t_turn = time.monotonic()
            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for b in msg.content:
                    if not isinstance(b, ToolResultBlock):
                        continue
                    name, inp, t0 = pending.pop(b.tool_use_id, ("?", {}, time.monotonic()))
                    parsed = core.parse_tool_result(b.content)
                    err, esc = core.result_flags(parsed, b.is_error)
                    if esc:
                        escalations.append(parsed["escalation"])
                        e0 = parsed["escalation"] if isinstance(parsed["escalation"], dict) else {}
                        why.append(why_line(e0.get("message") or e0.get("reason") or "Blocked by shop rules",
                                            [{"name": "Senso", "ref": e0.get("rule_id")}] if e0.get("rule_id") else None))
                    if name == "emit_event" and not err:
                        ev = inp.get("event") if isinstance(inp.get("event"), dict) else inp
                        if ev.get("type") in ("part.chosen", "part.rejected", "escalation") and ev.get("reason"):
                            why.append(why_line(ev["reason"], ev.get("sources")))
                    if name == "verify_owner" and isinstance(parsed, dict) and parsed.get("hosted_url"):
                        reply.persona_url = str(parsed["hosted_url"])
                    order = actions.on_result(b.tool_use_id, name, parsed, err, esc)
                    if order:
                        reply.orders.append(order)
                    if (n := _notes(name, parsed)):
                        notes.append(n)
                    tracker.tool_call(name, inp, parsed, (time.monotonic() - t0) * 1000, not err)
                t_turn = time.monotonic()
            elif isinstance(msg, ResultMessage):
                reply.cost_usd = msg.total_cost_usd
                if msg.is_error:
                    reply.error = f"{msg.subtype}: {'; '.join(msg.errors or []) or msg.terminal_reason or ''}"
                if msg.result:
                    last_text = msg.result
                tracker.run_cost(msg.total_cost_usd, msg.usage, msg.duration_ms, options.model or "")
    except Exception as e:  # noqa: BLE001
        reply.error = f"{type(e).__name__}: {e}"
        print(f"[sal.chat] turn failed: {reply.error}", file=sys.stderr)
    finally:
        body, ask = split_needs_owner(clean_text(last_text))
        if not ask and escalations:
            e0 = escalations[-1] if isinstance(escalations[-1], dict) else {}
            ask = str(e0.get("message") or e0.get("reason") or "Blocked by shop rules")[:120]
        if not body:
            body = "Hit a snag on that one. Try me again in a minute." if reply.error else "Done."
        reply.text, reply.needs_owner = body, ask
        # chosen first, then rejections/blocks; keep it to 3 lines
        why.sort(key=lambda w: 0 if "chose" in w.lower() or "pick" in w.lower() else 1)
        reply.why = why[:3]
        if ask:
            actions.set("act_" + uuid.uuid4().hex[:10], "approval", "waiting_owner", ask)
        reply.actions = list(actions.state.values())
        emit.message("sal", body + (f"\nNeeds your OK: {ask}" if ask else ""))
        append_history(chat_id, "sal", body + (f"\n(Waiting on owner OK: {ask})" if ask else ""),
                       "; ".join(notes)[:1500] or None, reply.why)
        tracker.end(reply)
    return reply


def run_chat(chat_id: Any, text: str, history: list[dict] | None = None, **kw: Any) -> ChatReply:
    return asyncio.run(run_chat_async(chat_id, text, history, **kw))
