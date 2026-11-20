"""Pure helpers of agent/telegram_bot.py (no network)."""
from agent import telegram_bot as tb


def test_format_event_key_types():
    assert tb.format_event({"type": "part.chosen", "summary": "Denso @ Mission $41"}).startswith("Chose:")
    line = tb.format_event({"type": "order.placed", "summary": "Mission order ORD-1",
                            "data": {"eta": "2026-11-16T10:20:00-08:00"}})
    assert "ETA 10:20 AM" in line
    esc = tb.format_event({"type": "escalation", "summary": "Alternator $260 over cap", "reason": "R1"})
    assert esc.startswith("NEEDS OWNER") and "R1" in esc
    assert "Wholesale $41.00" in tb.format_event({"type": "sal.summary", "summary": "s", "reason": "done",
                                                 "money": {"wholesale": 41, "retail": 82}})
    assert tb.format_event({"type": "context.retrieved", "summary": "x"}) is None


def test_hosted_url_and_kind(monkeypatch):
    monkeypatch.setattr(tb, "SIM_API", "http://127.0.0.1:9")  # nothing listens -> inference path
    ev = {"type": "escalation", "summary": "s", "data": {"hosted_url": "https://withpersona.com/verify?x"}}
    assert tb.hosted_url(ev).startswith("https://withpersona.com")
    assert tb.approval_kind(ev, "RO-1047") == "identity"
    assert tb.approval_kind({"type": "escalation", "refs": {"ro_id": "RO-1"}}, "RO-1") == "order"


def test_day_prefix_and_time():
    m = tb.DAY_CMD.match("/tue F-150 alternator")
    assert m and m.group(1) == "tue"
    assert tb.short_time("2026-11-16T15:05:00-08:00") == "3:05 PM"


def test_token_scrubbed():
    b = tb.Bot("123:SECRET")
    assert "SECRET" not in b._scrub("https://api.telegram.org/bot123:SECRET/getMe failed")
