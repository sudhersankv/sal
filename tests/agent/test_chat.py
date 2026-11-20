"""agent/chat.py pieces that don't need Claude."""
import json
from datetime import datetime
from pathlib import Path

import jsonschema

from agent import chat

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/events.schema.json").read_text(encoding="utf-8"))


def test_run_id_and_needs_owner():
    assert chat.chat_run_id(42, datetime(2026, 11, 20, tzinfo=chat.PT)) == "chat-42-20261120"
    body, ask = chat.split_needs_owner("Alternator is $260 at Mission.\nNEEDS_OWNER: Alternator $260 at Mission")
    assert body == "Alternator is $260 at Mission." and ask == "Alternator $260 at Mission"
    assert chat.split_needs_owner("Done.") == ("Done.", None)


def test_history_roundtrip_and_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(chat, "chat_dir", lambda: tmp_path)
    chat.append_history("c1", "user", "are we low?")
    chat.append_history("c1", "sal", "Short 4 items, $100.", "plan_restock: OF-CIVICx1, WIPER-22x4")
    h = chat.load_history("c1")
    assert [r["role"] for r in h] == ["user", "sal"]
    p = chat.render_prompt(h, "yea go get them", datetime(2026, 11, 20, 14, 5, tzinfo=chat.PT))
    assert "Them: are we low?" in p and "[Sal did: plan_restock: OF-CIVICx1" in p and p.endswith("yea go get them")
    for i in range(30):
        chat.append_history("c1", "user", f"m{i}")
    assert len(chat.load_history("c1")) == chat.HISTORY_TURNS


class FakeEmit:
    def __init__(self):
        self.events = []

    def __call__(self, type, actor, summary, **extra):
        self.events.append({"type": type, "actor": actor, "summary": summary, **extra})


def test_action_lifecycle():
    em = FakeEmit()
    a = chat.Actions(em)
    a.on_result("u0", "plan_restock", {"lines": [{"sku": "OF-CIVIC", "order_qty": 1}]}, False, False)
    a.on_use("u1", "place_shopify_order", {"lines": [{"sku": "OF-CIVIC", "qty": 1}]})
    order = a.on_result("u1", "place_shopify_order", {"shopify_order_id": "PDO-1", "total": 100.0, "eta": "x"},
                        False, False)
    assert order["order_id"] == "PDO-1"
    a.on_use("u2", "place_counter_order", {"vendor_id": "mission", "sku": "ALT", "ro_id": "RO-1047"})
    a.on_result("u2", "place_counter_order", {"escalation": {"rule_id": "R1"}}, False, True)
    statuses = [(e["data"]["kind"], e["data"]["status"]) for e in em.events]
    assert statuses == [("restock", "planned"), ("restock", "in_progress"), ("restock", "done"),
                        ("order", "in_progress"), ("order", "refused")]
    assert em.events[2]["refs"]["order_id"] == "PDO-1" and em.events[3]["refs"]["ro_id"] == "RO-1047"


def test_chat_events_match_schema():
    from sim.emit import build

    captured = []
    ev = build("chat-7-20261120", "fri", "2026-11-20T14:05:00-08:00", "chat.message", "owner", "are we low?",
               data={"channel": "telegram", "chat_id": "7", "text": "are we low?"})
    captured.append(ev)
    ev2 = build("chat-7-20261120", "fri", "2026-11-20T14:05:00-08:00", "action.status", "sal", "Restock — done",
                data={"action_id": "act_1", "kind": "restock", "status": "done", "title": "Restock"},
                refs={"order_id": "PDO-1"})
    captured.append(ev2)
    for e in captured:
        jsonschema.validate(e, SCHEMA)


def test_clean_text_and_why_line():
    assert chat.clean_text("## Done\n**Cap:** over") == "Done\nCap: over"
    w = chat.why_line("Denso, preferred brand, ETA beats promise", [{"name": "Senso", "ref": "R7"}, {"name": "SIE"}])
    assert w.endswith("(sources: Senso R7, SIE)")


def test_waiting_items_and_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from agent import chat_api
    from agent import sal as core

    monkeypatch.setattr(core, "ROOT", tmp_path)
    monkeypatch.setattr(chat, "chat_dir", lambda: tmp_path / "chat")
    log = tmp_path / "runs" / "chat-ui-20261120" / "events.jsonl"
    log.parent.mkdir(parents=True)
    rows = [{"type": "action.status", "data": {"action_id": "a1", "status": "waiting_owner", "title": "Alt $260"}},
            {"type": "action.status", "data": {"action_id": "a2", "status": "waiting_owner", "title": "Rule"}},
            {"type": "action.status", "data": {"action_id": "a2", "status": "done", "title": "Rule"}}]
    log.write_text(chr(10).join(json.dumps(r) for r in rows), encoding="utf-8")
    assert [a["title"] for a in chat.waiting_items("ui")] == ["Alt $260"]

    monkeypatch.setattr(chat, "run_chat", lambda cid, text, h=None, **kw: chat.ChatReply(text=f"echo {text}", run_id="r"))
    c = TestClient(chat_api.app)
    out = c.post("/chat", json={"chat_id": "ui", "text": "are we low?"}).json()
    assert out["reply"] == "echo are we low?" and out["actions"] == []
    assert c.get("/chat/ui/waiting").json()["waiting"][0]["title"] == "Alt $260"
