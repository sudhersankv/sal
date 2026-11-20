"""Fast sim tests: clock, trigger payloads, metrics math, stub Monday log validity."""
from __future__ import annotations

from datetime import datetime

import pytest

from sim import metrics
from sim.actors import Actors, car_owner_reply
from sim.clock import PST, WEEK_ORDER, SimClock, day_start, next_day
from sim.triggers import trigger_for


def test_week_dates_and_start_times():
    assert day_start("mon") == datetime(2026, 11, 16, 9, 12, tzinfo=PST)
    assert day_start("wed").isoformat() == "2026-11-18T07:30:00-08:00"
    assert day_start("fri").isoformat() == "2026-11-20T16:00:00-08:00"
    assert day_start("sun").isoformat() == "2026-11-22T18:00:00-08:00"
    assert WEEK_ORDER == ("mon", "tue", "wed", "fri", "sun")


def test_clock_is_monotonic():
    c = SimClock("mon")
    c.advance(minutes=30)
    assert c.iso() == "2026-11-16T09:42:00-08:00"
    c.advance_to(day_start("mon"))  # earlier -> ignored
    assert c.iso() == "2026-11-16T09:42:00-08:00"


def test_next_day():
    assert next_day(None) == "mon"
    assert next_day("tue") == "wed"
    assert next_day("wed") == "fri"
    assert next_day("sun") is None


def test_monday_trigger(monkeypatch):
    monkeypatch.setenv("SAL_HERO_VIN", "1HGTESTVIN0000001")
    t = trigger_for("mon")
    assert t["text"] == "Civic in bay 2, P0141, VIN 1HGTESTVIN0000001, customer promised by 3 PM"
    assert t["ro_id"] == "RO-1042" and t["dtc"] == "P0141" and t["bay"] == 2
    assert t["sim_ts"] == "2026-11-16T09:12:00-08:00"


def test_other_triggers():
    tue = trigger_for("tue")
    assert tue["quoted_wholesale"] == 260.0 and tue["part_type"] == "alternator"
    fri = trigger_for("fri")
    assert fri["path"].startswith("seed/statements/") and fri["vendor_id"] == "bayshore"
    assert trigger_for("wed")["task"] == "restock"
    assert trigger_for("sun")["task"] == "weekly_review"
    with pytest.raises(ValueError):
        trigger_for("thu")


def test_replay_metrics_math():
    late, price = dict(metrics.DEFAULT_LATE_RATE), dict(metrics.DEFAULT_STARTER_PRICE)
    off = metrics.replay_starter(False, late, price, jobs=8)
    on = metrics.replay_starter(True, late, price, jobs=8)
    assert off.on_time_pct == pytest.approx(62.5)
    assert on.on_time_pct == pytest.approx(95.0)
    assert off.expected_late_penalty == pytest.approx(3 * metrics.LATE_PENALTY_USD)
    assert on.expected_late_penalty == pytest.approx(0.4 * metrics.LATE_PENALTY_USD)
    assert off.escalations == pytest.approx(3.0)
    assert off.avg_cost == 148.0 and on.avg_cost == 163.0


def test_run_metrics_from_events():
    evs = [
        {"type": "order.placed", "money": {"wholesale": 41}},
        {"type": "order.placed", "money": {"wholesale": 259}},
        {"type": "order.delivered", "data": {"on_time": True}},
        {"type": "order.delivered", "data": {"on_time": False}},
        {"type": "escalation"},
    ]
    m = metrics.run_metrics(evs, "gate_off")
    assert (m.jobs, m.on_time_pct, m.escalations, m.avg_cost) == (2, 50.0, 1.0, 150.0)
    assert m.expected_late_penalty == metrics.LATE_PENALTY_USD
    assert metrics.run_metrics([], "x").on_time_pct == 100.0


def test_vendor_stats_prefers_scorecard():
    evs = [{"type": "scorecard.built", "data": {"per_vendor": [{"vendor_id": "bayshore", "late_rate": 0.5}]}}]
    late, _ = metrics.vendor_stats_from_events(evs)
    assert late["bayshore"] == 0.5 and late["mission"] == metrics.DEFAULT_LATE_RATE["mission"]


def test_actors_auto_and_interactive():
    a = Actors(interactive=False, delay_s=0)
    assert a.wait("quote", "RO-1") == "approved"
    b = Actors(interactive=True)
    b.request("rule", "r1")
    assert b.pending()[0]["id"] == "r1"
    b.decide("rule", "r1", approved=False)
    assert b.wait("rule", "r1", timeout=0.1) == "declined"


def test_dana_persona():
    assert car_owner_reply(82)["status"] == "approved"
    assert car_owner_reply(150)["status"] == "approved"
    assert car_owner_reply(151)["status"] == "question"


def test_stub_monday_log_is_schema_valid(tmp_path, monkeypatch):
    from sim import emit, run

    monkeypatch.setattr(emit, "RUNS", tmp_path)
    monkeypatch.setenv("SIM_STUB_AGENT", "1")
    monkeypatch.setenv("SIM_LOCAL_EMIT", "1")
    monkeypatch.setenv("SIM_NO_UI_POST", "1")
    monkeypatch.setenv("SIM_OFFLINE", "1")
    monkeypatch.setattr(emit, "_tools_emit", None)
    monkeypatch.setattr(metrics, "ROOT", tmp_path)
    run.configure(interactive=False, delay_s=0)
    run.run_day("mon", "pytest-mon", "off")
    evs = emit.read_log("pytest-mon")
    assert all(not emit.validate(e) for e in evs)
    types = [e["type"] for e in evs]
    for t in ("repair_order.created", "part.rejected", "part.chosen", "approval.received", "order.placed",
              "order.delivered", "sal.summary", "metrics.updated"):
        assert t in types, t
    assert types.index("order.placed") < types.index("order.delivered")
    ts = [e["ts"] for e in evs]
    assert ts == sorted(ts)
