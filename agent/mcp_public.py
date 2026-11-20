"""Public "Sal" MCP server: a front door for any personal agent (Claude, ChatGPT, Muse, ...) onto the SAME chat
brain as Telegram and the dashboard (agent.chat.run_chat: same memory, action list, policy and approvals).

Distinct from the internal `sal-tools` server: no raw place_* / order tools here. Spend only happens through
Sal, inside the shop's rules; over-cap approvals need the Persona-verified owner.

    python -m agent.mcp_public                         # stdio
    python -m agent.mcp_public --http --port 8103      # Streamable HTTP at /mcp, needs SAL_MCP_TOKEN (Bearer)
"""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer

from agent import chat
from agent import sal as core

INSTRUCTIONS = (
    "Sal is the parts department of Mission Street Auto (an independent repair shop). Talk to Sal like you'd "
    "text the shop's parts guy: use ask_sal for anything free-form (stock questions, sourcing a part for a car "
    "on a lift, 'go ahead and order those', order status, vendor questions). Sal acts inside the owner's rules: "
    "$200 spend cap, no-buy brands, preferred vendors. Use list_waiting/decide for things waiting on the owner, "
    "why for the reasoning and sources behind any order or action. Read-only views: get_today, get_inventory, "
    "get_orders, get_vendor_scorecards."
)
mcp = MCPServer("Sal", instructions=INSTRUCTIONS)


def _thread(caller: str | None) -> str:
    return "mcp-" + (re.sub(r"[^\w-]", "_", (caller or "mcp").strip())[:40] or "mcp")


async def _chat(chat_id: str, text: str) -> chat.ChatReply:
    # run_chat drives its own event loop + sync I/O: keep it off the server loop
    return await asyncio.to_thread(chat.run_chat, chat_id, text, None, actor="owner", channel="mcp")


def _amount(title: str) -> float:
    vals = [float(v.replace(",", "")) for v in re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", title or "")]
    return max(vals) if vals else 0.0


def _cap() -> float:
    try:
        return float(os.getenv("SPEND_CAP", "200"))
    except ValueError:
        return 200.0


def _query(sql: str, params: tuple = ()) -> list[dict]:
    from tools import data

    rows, _ = data.query(sql, params)
    return rows


# ---------------------------------------------------------------- tools


@mcp.tool()
async def ask_sal(message: str, caller: str = "mcp") -> dict:
    """Text Sal, the shop's parts guy, in plain language and get his reply. Same brain as the shop's Telegram chat.

    Examples: "are we low for the Civics next week?", "yea go get them", "Civic in bay 2, P0141, VIN ...,
    promised 3pm", "where's the Bosch order?", "is Bayshore still late on alternators?".
    Sal decides what to do and may place orders within the owner's rules (spend cap $200, no-buy list, preferred
    vendors). Anything over the cap or a rule change comes back as waiting on the owner (see list_waiting).
    `caller` names your agent; each caller gets its own conversation thread with memory of earlier turns.
    Returns {summary, reply, needs_owner, actions[], orders[], why[]}.
    """
    r = await _chat(_thread(caller), message)
    return {"summary": r.text.splitlines()[0][:200] if r.text else "", "reply": r.text, "needs_owner": r.needs_owner,
            "actions": r.actions, "orders": r.orders, "why": r.why, "persona_url": r.persona_url, "error": r.error}


_MAX_BILL_BYTES = 15 * 1024 * 1024
_BILL_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".csv", ".heic"}


@mcp.tool()
async def send_bill(filename: str, file_base64: str | None = None, url: str | None = None, note: str = "",
                    caller: str = "mcp") -> dict:
    """Hand Sal a vendor bill, invoice or statement (photo or PDF), exactly like sending it to Sal on Telegram.

    Sal reads it (OCR / document parsing), reconciles every line against what the shop bought, and reports what's
    off, e.g. core credits the vendor never paid back, and drafts a dispute (it never sends it). Give the file
    either as `file_base64` (raw bytes, base64-encoded) or as an https `url`. `filename` should keep its extension
    (.pdf, .png, .jpg, .jpeg, .webp, .csv). Max 15 MB. `note` is optional context ("Bayshore's November statement").
    Returns the same shape as ask_sal.
    """
    import base64
    import re as _re

    ext = Path(filename).suffix.lower()
    if ext not in _BILL_EXTS:
        return {"error": f"unsupported file type {ext or '(none)'}; send a PDF, image or CSV"}
    try:
        if file_base64:
            data = base64.b64decode(file_base64.split(",", 1)[-1], validate=False)
        elif url and url.startswith("https://"):
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
                r = await c.get(url)
                r.raise_for_status()
                data = r.content
        else:
            return {"error": "give file_base64 or an https url"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"couldn't read the file: {type(e).__name__}"}
    if not data or len(data) > _MAX_BILL_BYTES:
        return {"error": "file is empty or over 15 MB"}
    thread = _thread(caller)
    safe = _re.sub(r"[^\w.\-]", "_", Path(filename).name)
    dest = chat.chat_dir() / "files" / _re.sub(r"[^\w.\-]", "_", str(thread)) / safe
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    text = (f"I just sent you a vendor bill/statement, saved at {dest.as_posix()}. "
            f"Read it, reconcile it against what we bought, tell me what's off. {note}").strip()
    r = await _chat(thread, text)
    return {"summary": r.text.splitlines()[0][:200] if r.text else "", "reply": r.text, "needs_owner": r.needs_owner,
            "actions": r.actions, "orders": r.orders, "why": r.why, "persona_url": r.persona_url, "error": r.error,
            "saved_as": safe}


def _today() -> dict:
    now = datetime.now(chat.PT)
    today, week_start = now.strftime("%Y-%m-%d"), (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    open_orders = _query("SELECT order_id, vendor_id, ro_id, placed_at, promised_at, total, channel FROM orders "
                         "WHERE delivered_at IS NULL ORDER BY promised_at")
    arriving = [o for o in open_orders if str(o.get("promised_at") or "").startswith(today)]
    late = [o for o in open_orders if o.get("promised_at") and str(o["promised_at"]) < now.strftime("%Y-%m-%d %H:%M")]
    spend = sum(float(o.get("total") or 0) for o in _query("SELECT total FROM orders WHERE placed_at >= %s",
                                                            (week_start + " 00:00:00",)))
    low = [i for i in _query("SELECT sku, name, qty, min_qty FROM inventory") if int(i["qty"]) <= int(i["min_qty"])]
    waiting = chat.waiting_items("*")
    summary = (f"{len(waiting)} waiting on owner, {len(arriving)} arriving today, {len(late)} late, "
               f"{len(low)} low items, ${spend:,.2f} spent this week")
    return {"summary": summary, "date": today, "waiting_on_owner": [_waiting_out(a) for a in waiting],
            "arriving_today": arriving, "late_orders": late, "low_stock": low, "spend_this_week": round(spend, 2)}


@mcp.tool()
def get_today() -> dict:
    """Today's brief for the shop: what's waiting on the owner, orders arriving today, late orders, items at or
    below minimum stock, and parts spend so far this week. Read-only, no side effects."""
    return _today()


def _waiting_out(a: dict) -> dict:
    return {"action_id": a.get("action_id"), "kind": a.get("kind"), "title": a.get("title"),
            "amount": _amount(a.get("title", "")) or None, "refs": a.get("refs"), "since": a.get("ts"),
            "over_cap": _amount(a.get("title", "")) > _cap(), "why": chat.last_why(a.get("chat_id", ""))[:3]}


@mcp.tool()
def list_waiting() -> dict:
    """Everything Sal has waiting on the shop owner (over-cap orders, quotes, rule proposals, disputes), across
    Telegram, the dashboard and MCP. Returns {summary, waiting:[{action_id, kind, title, amount, over_cap, why[]}]}.
    Use decide(action_id, ...) to answer one."""
    items = [_waiting_out(a) for a in chat.waiting_items("*")]
    return {"summary": f"{len(items)} waiting on the owner" if items else "Nothing waiting on the owner.",
            "waiting": items}


def _persona_link(title: str, ro_id: str | None) -> dict:
    """Start an owner identity check without auto-approving it; returns {inquiry_id, status, hosted_url}."""
    try:
        from tools import impl

        prev = os.environ.get("SAL_OWNER_VERIFY_MODE")
        os.environ["SAL_OWNER_VERIFY_MODE"] = "pending"
        try:
            return impl.verify_owner(f"Approval requested via MCP: {title}", _amount(title), ro_id) or {}
        finally:
            if prev is None:
                os.environ.pop("SAL_OWNER_VERIFY_MODE", None)
            else:
                os.environ["SAL_OWNER_VERIFY_MODE"] = prev
    except Exception as e:  # noqa: BLE001
        print(f"[sal.mcp] persona link failed: {type(e).__name__}", file=sys.stderr)
        return {}


@mcp.tool()
async def decide(action_id: str, approve: bool, note: str = "") -> dict:
    """Approve or decline one item from list_waiting, the same way the owner taps Approve/Decline on Telegram.

    Declines always go through. Approvals of anything over the $200 spend cap are NOT accepted from an agent:
    the shop owner must verify their identity with Persona first. In that case this returns status "pending"
    and a persona_url for the owner to open; nothing is ordered. Do not try to work around this.
    Returns {summary, status: done|pending|not_found, reply?, persona_url?}.
    """
    a = chat.action_index("*").get(action_id)
    if not a or a.get("status") != "waiting_owner":
        return {"summary": f"No open item {action_id}.", "status": "not_found"}
    title, cid = a.get("title", ""), a.get("chat_id") or "mcp-mcp"
    if approve and (_amount(title) > _cap() or a.get("kind") in ("verification", "rule")):
        p = _persona_link(title, (a.get("refs") or {}).get("ro_id"))
        url = p.get("hosted_url") or None
        return {"summary": "Owner must approve this one personally (over the spend cap or a rule change). "
                           + ("Send them the Persona link." if url else "Ask them to approve on Telegram or the dashboard."),
                "status": "pending", "persona_url": url, "inquiry_id": p.get("inquiry_id"), "title": title}
    text = ("Approved, go ahead." if approve else "Declined. Don't do it.") + (f" {note}" if note else "")
    r = await _chat(cid, text)
    return {"summary": r.text.splitlines()[0][:200] if r.text else "", "status": "done", "reply": r.text,
            "actions": r.actions, "orders": r.orders}


def _events_all() -> list[dict]:
    out = []
    for p in (core.ROOT / "runs").glob("*/events.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


@mcp.tool()
def why(ref: str) -> dict:
    """Why did Sal do that? Give an order_id, repair order id (RO-1042), or action_id. Returns the short reasons
    (what was chosen, what was rejected and why, policy checks) with their sources (shop rules, purchase history,
    parts matcher, notes, NHTSA). Read-only."""
    evs = _events_all()
    hits = [e for e in evs if ref in json.dumps(e.get("refs") or {}) or (e.get("data") or {}).get("action_id") == ref]
    if not hits:
        return {"summary": f"Nothing on record for {ref}.", "ref": ref, "lines": []}
    run_ids = {e.get("run_id") for e in hits}
    ro = next((h["refs"].get("ro_id") for h in hits if (h.get("refs") or {}).get("ro_id")), None)
    related = [e for e in evs if e.get("run_id") in run_ids and e.get("type") in
               ("part.chosen", "part.rejected", "escalation", "order.placed", "identity.verified", "restock.planned")
               and (not ro or (e.get("refs") or {}).get("ro_id") in (None, ro))]
    related.sort(key=lambda e: 0 if e["type"] == "part.chosen" else 1)
    lines = [chat.why_line(e.get("reason") or e.get("summary", ""), e.get("sources")) for e in related[:6]]
    sources = sorted({s.get("name") for e in related for s in e.get("sources") or [] if s.get("name")})
    return {"summary": lines[0] if lines else hits[-1].get("summary", ""), "ref": ref, "lines": lines,
            "sources": sources}


@mcp.tool()
def get_inventory(filter: str = "low") -> dict:
    """Shop stock. filter: "low" (at or below minimum), "out" (zero on hand) or "all". Read-only."""
    rows = _query("SELECT sku, name, part_type, qty, min_qty, max_qty FROM inventory ORDER BY sku")
    if filter == "low":
        rows = [r for r in rows if int(r["qty"]) <= int(r["min_qty"])]
    elif filter == "out":
        rows = [r for r in rows if int(r["qty"]) <= 0]
    return {"summary": f"{len(rows)} items ({filter})", "items": rows}


@mcp.tool()
def get_orders(status: str = "open") -> dict:
    """Parts orders. status: "open" (not delivered), "delivered" or "all". Newest first. Read-only."""
    where = {"open": "WHERE delivered_at IS NULL", "delivered": "WHERE delivered_at IS NOT NULL"}.get(status, "")
    rows = _query("SELECT order_id, vendor_id, ro_id, placed_at, promised_at, delivered_at, total, channel "
                  f"FROM orders {where} ORDER BY placed_at DESC LIMIT 50")
    return {"summary": f"{len(rows)} {status} orders", "orders": rows}


@mcp.tool()
def get_vendor_scorecards(days: int = 90) -> dict:
    """Vendor scorecards over the last N days: orders, late deliveries and late rate, missed core credits and
    dollars, price index. Read-only."""
    from tools import impl

    out = impl.get_vendor_history(days=days) or {}
    per = out.get("per_vendor") or []
    worst = max(per, key=lambda v: v.get("late_rate", 0), default=None)
    summ = (f"Worst on-time: {worst['vendor_id']} {worst['late_rate'] * 100:.0f}% late" if worst else "No orders")
    return {"summary": summ, "vendors": per}


# ---------------------------------------------------------------- resources


@mcp.resource("sal://today", mime_type="application/json", description="Today's brief (same as get_today).")
def res_today() -> str:
    return json.dumps(_today(), default=str)


@mcp.resource("sal://inventory", mime_type="application/json", description="All stock levels.")
def res_inventory() -> str:
    return json.dumps(get_inventory("all"), default=str)


@mcp.resource("sal://activity", mime_type="application/json", description="Sal's 30 most recent actions.")
def res_activity() -> str:
    acts = sorted(chat.action_index("*").values(), key=lambda a: str(a.get("ts")), reverse=True)[:30]
    return json.dumps({"actions": acts}, default=str)


# ---------------------------------------------------------------- transports


class BearerAuth:
    """ASGI middleware: every HTTP request needs Authorization: Bearer <SAL_MCP_TOKEN>."""

    def __init__(self, app, token: str):
        self.app, self.expected = app, f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            got = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(got, self.expected):
                body = b'{"error":"unauthorized"}'
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def http_app(token: str):
    from mcp.server.transport_security import TransportSecuritySettings

    # bearer auth guards every request; DNS-rebinding host checks would block tunnel/public hostnames
    app = mcp.streamable_http_app(streamable_http_path="/mcp", host="0.0.0.0",
                                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    return BearerAuth(app, token)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m agent.mcp_public")
    ap.add_argument("--http", action="store_true", help="serve Streamable HTTP at /mcp instead of stdio")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8103)
    a = ap.parse_args(argv)
    core.load_env()
    if not a.http:
        mcp.run()
        return 0
    token = os.getenv("SAL_MCP_TOKEN")
    if not token:
        print("SAL_MCP_TOKEN is not set; refusing to serve HTTP without auth.", file=sys.stderr)
        return 2
    import uvicorn

    uvicorn.run(http_app(token), host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
