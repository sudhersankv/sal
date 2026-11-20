"""Sal staff chat on Telegram (T3 B6, D-010). `python -m agent.telegram_bot`

- Every message goes to Sal's chat mode (agent.chat.run_chat): Sal works out what's wanted and does it. A typing
  indicator shows while he works; one clean reply comes back. If the owner's OK is needed, the reply carries
  Approve/Decline buttons; a tap goes back to Sal as the owner's answer.
- Hidden demo commands: /mon /tue /wed /fri /sun run that sim day and stream key events (old B6 behaviour);
  their escalation buttons POST {SIM_API}/sim/approve, with a Persona hosted_url link if present.

Long-polls getUpdates with httpx. The bot token is read from TELEGRAM_BOT_TOKEN and never logged.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
import uuid
from typing import Any

import httpx

from agent import sal

SIM_API = os.getenv("SIM_API_URL", "http://localhost:8102")
POLL_TIMEOUT = 30
DAY_CMD = re.compile(r"^/(mon|tue|wed|thu|fri|sat|sun)\b\s*", re.I)
HELP = ("Sal here. Parts. Text me like you'd text your parts guy:\n"
        "- Civic in bay 2, P0141, VIN ..., promised by 3 PM\n"
        "- are we low on anything for next week?\n"
        "- who's been late on alternators?\n"
        "- or send me a vendor bill (PDF or photo)\n"
        "Shortcuts: /today /stock /orders /waiting /why")

WHY_BUTTON = {"text": "Why?", "callback_data": "ok|w"}
COMMANDS = {  # shortcuts; free text always works
    "/today": "Give me today's brief: what needs me, what arrives today, what's low for upcoming bookings, "
              "spend so far this week.",
    "/stock": "What's low right now against the next 7 days of bookings?",
    "/orders": "What orders are open, and when does each arrive? Flag anything late.",
}


def owner_buttons(persona_url: str | None = None) -> list[list[dict]]:
    rows = [[{"text": "Approve", "callback_data": "ok|1"}, {"text": "Decline", "callback_data": "ok|0"}, WHY_BUTTON]]
    if persona_url:
        rows.append([{"text": "Verify it's you (Persona)", "url": persona_url}])
    return rows


def why_text(chat_id: Any) -> str:
    from agent.chat import last_why

    lines = last_why(chat_id)
    return "\n".join(f"- {w}" for w in lines) if lines else "Nothing to explain yet. Ask me about a part or order."


def waiting_text(chat_id: Any) -> str:
    from agent.chat import waiting_items

    items = waiting_items(chat_id)
    if not items:
        return "Nothing waiting on you."
    return "Waiting on you:\n" + "\n".join(f"- {a.get('title')}" for a in items[-8:])

logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx INFO logs full URLs (token in path)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class Bot:
    def __init__(self, token: str):
        self._token = token
        self._base = f"https://api.telegram.org/bot{token}"
        self.http = httpx.Client(timeout=POLL_TIMEOUT + 10)
        self.busy: dict[int, str] = {}  # chat_id -> run_id

    # ------------------------------------------------------------ telegram API
    def _scrub(self, s: Any) -> str:
        return str(s).replace(self._token, "***")

    def call(self, method: str, **params: Any) -> Any:
        try:
            r = self.http.post(f"{self._base}/{method}", json=params)
            body = r.json()
            if not body.get("ok"):
                log(f"telegram {method} failed: {self._scrub(body.get('description'))}")
            return body.get("result")
        except Exception as e:  # noqa: BLE001
            log(f"telegram {method} error: {type(e).__name__}: {self._scrub(e)}")
            return None

    def send(self, chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> Any:
        params: dict[str, Any] = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        return self.call("sendMessage", **params)

    # ------------------------------------------------------------ loop
    def run_forever(self) -> None:
        me = self.call("getMe") or {}
        log(f"polling as @{me.get('username', '?')}")
        self.call("setMyCommands", commands=[
            {"command": "today", "description": "Today's brief"},
            {"command": "stock", "description": "What's low"},
            {"command": "orders", "description": "Open orders"},
            {"command": "waiting", "description": "Waiting on you"},
            {"command": "why", "description": "Why did Sal do that?"},
        ])
        offset = None
        while True:
            ups = self.call("getUpdates", timeout=POLL_TIMEOUT, offset=offset,
                            allowed_updates=["message", "callback_query"])
            if ups is None:
                time.sleep(3)
                continue
            for u in ups:
                offset = u["update_id"] + 1
                try:
                    m = u.get("message") or {}
                    if "callback_query" in u:
                        self.on_callback(u["callback_query"])
                    elif m.get("document") or m.get("photo"):
                        self.on_file(m)
                    elif m.get("text"):
                        self.on_message(m)
                except Exception as e:  # noqa: BLE001
                    log(f"update {u.get('update_id')} failed: {type(e).__name__}: {self._scrub(e)}")

    def on_message(self, m: dict) -> None:
        chat_id, text = m["chat"]["id"], m["text"].strip()
        if text.split()[0].lower() in ("/start", "/help"):
            self.send(chat_id, HELP)
            return
        if chat_id in self.busy:
            self.send(chat_id, "One sec, still on your last one.")
            return
        if (mt := DAY_CMD.match(text)):  # hidden demo commands
            day, text = mt.group(1).lower(), text[mt.end():].strip()
            threading.Thread(target=self.job, args=(chat_id, day, text, m.get("from") or {}), daemon=True).start()
            return
        cmd, _, arg = text.partition(" ")
        cmd = cmd.lower().split("@")[0]
        if cmd == "/waiting":
            self.send(chat_id, waiting_text(chat_id))
            return
        if cmd == "/why" and not arg.strip():
            self.send(chat_id, why_text(chat_id))
            return
        text = COMMANDS.get(cmd, text) if cmd in COMMANDS else (f"Why {arg}?" if cmd == "/why" else text)
        threading.Thread(target=self.chat, args=(chat_id, text), daemon=True).start()

    def on_file(self, m: dict) -> None:
        """Bill photo / PDF -> download -> Sal parses + reconciles it."""
        chat_id = m["chat"]["id"]
        if chat_id in self.busy:
            self.send(chat_id, "One sec, still on your last one.")
            return
        doc = m.get("document") or (m.get("photo") or [{}])[-1]  # largest photo size is last
        name = doc.get("file_name") or f"photo_{doc.get('file_unique_id', 'x')}.jpg"
        info = self.call("getFile", file_id=doc.get("file_id")) or {}
        if not info.get("file_path"):
            self.send(chat_id, "Couldn't pull that file down. Send it again?")
            return
        dest = sal.ROOT / "runs" / "chat" / "files" / str(chat_id) / re.sub(r"[^\w.\-]", "_", name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = self.http.get(f"https://api.telegram.org/file/bot{self._token}/{info['file_path']}")
            r.raise_for_status()
            dest.write_bytes(r.content)
        except Exception as e:  # noqa: BLE001
            log(f"file download failed: {type(e).__name__}")
            self.send(chat_id, "Couldn't pull that file down. Send it again?")
            return
        caption = (m.get("caption") or "").strip()
        text = (f"I just sent you a vendor bill/statement, saved at {dest.as_posix()}. "
                f"Read it, reconcile it against what we bought, tell me what's off. {caption}").strip()
        threading.Thread(target=self.chat, args=(chat_id, text), daemon=True).start()

    # ------------------------------------------------------------ chat mode
    def chat(self, chat_id: int, text: str, actor: str = "owner") -> None:
        self.busy[chat_id] = "chat"
        stop = threading.Event()

        def typing() -> None:
            while not stop.is_set():
                self.call("sendChatAction", chat_id=chat_id, action="typing")
                stop.wait(4.0)

        threading.Thread(target=typing, daemon=True).start()
        try:
            from agent.chat import run_chat

            r = run_chat(chat_id, text, actor=actor)
            stop.set()
            if r.needs_owner:
                self.send(chat_id, f"{r.text}\n\nNeeds your OK: {r.needs_owner}", owner_buttons(r.persona_url))
            elif r.why:
                self.send(chat_id, r.text, [[WHY_BUTTON]])
            else:
                self.send(chat_id, r.text)
        except Exception as e:  # noqa: BLE001
            stop.set()
            self.send(chat_id, "Hit a snag on that one. Try me again in a minute.")
            log(f"chat failed: {type(e).__name__}: {self._scrub(e)}")
        finally:
            stop.set()
            self.busy.pop(chat_id, None)

    def on_callback(self, q: dict) -> None:
        parts = (q.get("data") or "").split("|")
        msg = q.get("message") or {}
        if len(parts) == 2 and parts[0] == "ok" and msg:  # chat mode
            chat_id = msg["chat"]["id"]
            if parts[1] == "w":  # Why?
                self.call("answerCallbackQuery", callback_query_id=q["id"])
                self.call("sendMessage", chat_id=chat_id, text=why_text(chat_id),
                          reply_to_message_id=msg["message_id"])
                return
            yes = parts[1] == "1"
            self.call("answerCallbackQuery", callback_query_id=q["id"], text="Approved." if yes else "Declined.")
            # edit the original message in place: stamp the decision, keep only Why?
            self.call("editMessageText", chat_id=chat_id, message_id=msg["message_id"],
                      text=f"{msg.get('text', '')}\n\n{'✅ Approved' if yes else '❌ Declined'}"[:4000],
                      disable_web_page_preview=True, reply_markup={"inline_keyboard": [[WHY_BUTTON]]})
            if chat_id not in self.busy:
                answer = "Approved, go ahead." if yes else "Declined. Don't order it."
                threading.Thread(target=self.chat, args=(chat_id, answer), daemon=True).start()
            return
        if len(parts) != 4 or parts[0] != "ap":
            return
        _, kind, ap_id, yes = parts
        approved = yes == "1"
        ok = False
        try:
            r = httpx.post(f"{SIM_API}/sim/approve", json={"kind": kind, "id": ap_id, "approved": approved},
                           timeout=5)
            ok = r.status_code < 300
        except Exception as e:  # noqa: BLE001
            log(f"sim approve failed: {type(e).__name__}")
        verdict = "Approved" if approved else "Declined"
        self.call("answerCallbackQuery", callback_query_id=q["id"],
                  text=f"{verdict}." if ok else "Sim didn't take it. Is sim.api up on :8102?")
        if ok and msg:
            who = (q.get("from") or {}).get("first_name", "owner")
            self.call("editMessageReplyMarkup", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
                      reply_markup={"inline_keyboard": []})
            self.send(msg["chat"]["id"], f"{verdict} by {who} ({kind} {ap_id}).")

    # ------------------------------------------------------------ one Sal run
    def job(self, chat_id: int, day: str, text: str, sender: dict) -> None:
        run_id = f"tg-{day}-{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"
        self.busy[chat_id] = run_id
        try:
            ro = (re.search(r"\bRO-\d+\b", text, re.I) or [None])[0] or f"RO-{1100 + int(time.time()) % 900}"
            sim_ts = sal.DEFAULT_SIM_TS[day]
            trigger: dict[str, Any] = {"text": text, "channel": "telegram", "actor": "tech", "ro_id": ro,
                                       "telegram_chat_id": chat_id}
            if text and day in ("mon", "tue"):
                trigger["kind"] = "tech_message"  # we log repair_order.created here; Sal must not repeat it
                emit_event(run_id, day, sim_ts, "repair_order.created", "tech", text[:140],
                           sources=[{"name": "Shop", "ref": "telegram"}],
                           refs={"ro_id": ro, "telegram_chat_id": str(chat_id)},
                           data={"channel": "telegram", "from": sender.get("first_name")})
            elif not text:
                trigger = sal.DEFAULT_TRIGGERS.get(day) or None
            self.send(chat_id, "On it.")
            variant = os.getenv("SAL_VARIANT", "off")
            box: dict[str, Any] = {}
            t = threading.Thread(target=lambda: box.update(res=sal.run_day(day, trigger, variant, run_id, sim_ts)),
                                 daemon=True)
            t.start()
            seen = 0
            while True:
                alive = t.is_alive()
                events = read_events(run_id)
                for ev in events[seen:]:
                    self.post_event(chat_id, ev, ro)
                seen = len(events)
                if not alive:
                    break
                time.sleep(1.0)
            res = box.get("res")
            if res is not None and not res.ok:
                self.send(chat_id, f"Run ended badly: {self._scrub(res.error)[:300]}")
        except Exception as e:  # noqa: BLE001
            self.send(chat_id, f"Sal fell over: {type(e).__name__}")
            log(f"job failed: {type(e).__name__}: {self._scrub(e)}")
        finally:
            self.busy.pop(chat_id, None)

    def post_event(self, chat_id: int, ev: dict, ro: str) -> None:
        typ, refs = ev.get("type"), ev.get("refs") or {}
        line = format_event(ev)
        if not line:
            return
        if typ == "escalation" or needs_owner_identity(ev):
            url = hosted_url(ev)
            if url:
                line += f"\nVerify owner (Persona): {url}"
            ap_id = refs.get("ro_id") or refs.get("rule_id") or ro
            kind = approval_kind(ev, ap_id)
            self.send(chat_id, line, [[{"text": "Approve", "callback_data": f"ap|{kind}|{ap_id}|1"[:64]},
                                       {"text": "Decline", "callback_data": f"ap|{kind}|{ap_id}|0"[:64]}]])
            return
        self.send(chat_id, line)


# ---------------------------------------------------------------- pure helpers (unit-tested)


def _tag(label: str, s: str) -> str:
    """Prefix a label unless Sal's summary already starts with a verb ("Choose ...", "Reject ...")."""
    return s if re.match(r"^(chos|choose|reject|pass|order|bought|deliver)", s, re.I) else f"{label}: {s}"


def format_event(ev: dict) -> str | None:
    """Terse chat line for the events a tech/owner cares about; None for the rest."""
    typ, s = ev.get("type"), ev.get("summary", "")
    data, money = ev.get("data") or {}, ev.get("money") or {}
    if typ == "part.chosen":
        return _tag("Chose", s)
    if typ == "part.rejected":
        return _tag("Passed", s)
    if typ == "order.placed":
        eta = data.get("eta") or (ev.get("refs") or {}).get("eta")
        return _tag("Ordered", s) + (f". ETA {short_time(eta)}" if eta else "")
    if typ == "order.delivered":
        return f"Delivered: {s}"
    if typ == "approval.received":
        return f"Customer: {s}"
    if typ == "escalation":
        reason = ev.get("reason") or ""
        return f"NEEDS OWNER: {s}" + (f"\n{reason}" if reason and reason != s else "")
    if needs_owner_identity(ev):
        return f"Owner ID check pending: {s}"
    if typ == "sal.summary":
        out = ev.get("reason") or s
        if money.get("wholesale") is not None:
            out += f"\nWholesale ${money['wholesale']:.2f}" + (
                f", retail ${money['retail']:.2f}" if money.get("retail") is not None else "")
        return out
    return None


def needs_owner_identity(ev: dict) -> bool:
    """verify_owner left pending: tools emit approval.requested with a Persona source."""
    if ev.get("type") == "identity.verified":
        return (ev.get("data") or {}).get("status") == "pending"
    return ev.get("type") == "approval.requested" and any(
        s.get("name") == "Persona" for s in ev.get("sources") or [])


def short_time(ts: str) -> str:
    m = re.search(r"T(\d{2}):(\d{2})", str(ts))
    if not m:
        return str(ts)
    h, mi = int(m.group(1)), m.group(2)
    return f"{(h - 1) % 12 + 1}:{mi} {'AM' if h < 12 else 'PM'}"


def hosted_url(ev: dict) -> str | None:
    data = ev.get("data") or {}
    for k in ("hosted_url", "persona_url", "verify_url"):
        if data.get(k):
            return str(data[k])
    for src in ev.get("sources") or []:
        if src.get("name") == "Persona" and src.get("url"):
            return src["url"]
    return None


def approval_kind(ev: dict, ap_id: str) -> str:
    """Prefer what the sim is actually waiting on; else infer."""
    try:
        pend = httpx.get(f"{SIM_API}/sim/state", timeout=2).json().get("pending") or []
        for p in pend:
            if p.get("id") == ap_id:
                return p["kind"]
    except Exception:  # noqa: BLE001
        pass
    refs = ev.get("refs") or {}
    if ev.get("type") in ("identity.verified", "approval.requested") or hosted_url(ev):
        return "identity"
    if refs.get("rule_id") and not refs.get("ro_id") and ev.get("type") == "rule.proposed":
        return "rule"
    return "order"


def read_events(run_id: str) -> list[dict]:
    from sim.emit import read_log

    return read_log(run_id)


def emit_event(run_id: str, day: str, ts: str, type: str, actor: str, summary: str, **extra: Any) -> dict:
    from sim.emit import build, emit

    return emit(build(run_id, day, ts, type, actor, summary, **extra))


def log(msg: str) -> None:
    print(f"[sal.telegram] {msg}", file=sys.stderr, flush=True)


def main() -> int:
    sal.load_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        log("TELEGRAM_BOT_TOKEN not set")
        return 1
    try:
        Bot(token).run_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
