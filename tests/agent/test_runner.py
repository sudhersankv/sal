"""Cheap unit tests for agent/sal.py (no API calls, no tool server)."""
import json
from pathlib import Path

import jsonschema
import pytest

from agent import analytics, sal

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/events.schema.json").read_text(encoding="utf-8"))


def test_options_lock_sal_to_sal_tools(monkeypatch):
    monkeypatch.setenv("SAL_MODEL", "claude-test-model")
    o = sal.build_options("mon", "r1", "2026-11-16T09:12:00-08:00", "on")
    assert o.tools == []
    assert o.allowed_tools == ["mcp__sal-tools__*"]
    assert "mcp__sal-tools__approve_rule" in o.disallowed_tools
    assert o.model == "claude-test-model"
    assert o.max_turns and o.max_turns <= 60
    assert o.setting_sources == []
    assert o.strict_mcp_config
    srv = o.mcp_servers["sal-tools"]
    assert srv["args"] == ["-m", "tools.server"]
    env = srv["env"]
    assert env["SAL_RUN_ID"] == "r1" and env["SAL_DAY"] == "mon" and env["SAL_VARIANT"] == "on"
    assert env["SAL_SIM_TS"].startswith("2026-11-16")
    assert not any("KEY" in k or "SECRET" in k for k in env), "secrets must not be forwarded explicitly"


def test_system_prompt_has_procedures_and_context():
    p = sal.build_system_prompt("wed", "r2", "2026-11-18T07:30:00-08:00", "off")
    for day in ("### MON", "### TUE", "### WED", "### FRI", "### SUN"):
        assert day in p
    for tool in ("verify_owner", "search_shop_data", "plan_restock", "place_shopify_order",
                 "parse_vendor_statement", "reconcile_statement", "recall_facts", "propose_rule"):
        assert tool in p
    assert "sal.summary" in p and "variant (Statsig arm, chosen by sim): off" in p


def test_user_prompt_with_and_without_trigger():
    assert "No one asked" in sal.build_user_prompt("wed", None, "t")
    assert "P0141" in sal.build_user_prompt("mon", sal.DEFAULT_TRIGGERS["mon"], "t")


@pytest.mark.parametrize("content,expected", [
    ('{"a": 1}', {"a": 1}),
    ([{"type": "text", "text": '{"error": {"code": "x"}}'}], {"error": {"code": "x"}}),
    ("plain", "plain"),
])
def test_parse_tool_result(content, expected):
    assert sal.parse_tool_result(content) == expected


def test_result_flags():
    assert sal.result_flags({"error": {}}, False) == (True, False)
    assert sal.result_flags({"escalation": {}}, None) == (False, True)
    assert sal.result_flags({"ok": 1}, True) == (True, False)
    assert sal.result_flags("x", None) == (False, False)


def test_fallback_summary_matches_schema():
    res = sal.RunResult(run_id="r3", day="mon", variant="on", tool_calls=["decode_vin"] * 3)
    ev = sal.fallback_summary_event("mon", "r3", "2026-11-16T09:12:00-08:00", "on", "x" * 500, res)
    jsonschema.validate({"id": "evt_abc123", **ev}, SCHEMA)
    assert len(ev["summary"]) <= 140 and ev["type"] == "sal.summary"
    res.error = "max_turns"
    ev = sal.fallback_summary_event("mon", "r3", "2026-11-16T09:12:00-08:00", "on", "", res)
    assert "cut short" in ev["summary"]


def test_emit_direct_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(sal, "ROOT", tmp_path)
    monkeypatch.setenv("SAL_EVENTS_URL", "http://127.0.0.1:9/events")  # nothing listens
    ev = {"run_id": "r4", "ts": "2026-11-16T09:12:00-08:00", "day": "mon", "type": "sal.summary",
          "actor": "sal", "summary": "done"}
    assert sal.emit_direct(ev)
    line = json.loads((tmp_path / "runs/r4/events.jsonl").read_text(encoding="utf-8").strip())
    jsonschema.validate(line, SCHEMA)


def test_analytics_noop_without_key(monkeypatch):
    monkeypatch.delenv("AMPLITUDE_AI_API_KEY", raising=False)
    t = analytics.SessionTracker("r5", "mon", "off", "m")
    assert not t.enabled
    t.user_message("hi")
    t.ai_message("x", ["decode_vin"], 1.0, {}, "m", None)
    t.tool_call("decode_vin", {}, {}, 1.0, True)
    t.custom("sal_order_placed", {})
    t.end(sal.RunResult(run_id="r5", day="mon", variant="off"))
    assert t.session is None


def test_cli_rejects_bad_day():
    with pytest.raises(SystemExit):
        sal.main(["--day", "xyz"])


def test_normalize_variant_from_sim_dict():
    v = {"name": "on", "gate_routing_v2": True, "sal_vendor_routing_v2": True,
         "sal_policy": {"strategy": "rules_aware"}}
    name, env = sal.normalize_variant(v)
    assert name == "on" and env == {"SAL_GATE_ROUTING_V2": "1", "SAL_POLICY_STRATEGY": "rules_aware"}
    o = sal.build_options("sun", "w1", "2026-11-22T18:00:00-08:00", v)
    assert o.mcp_servers["sal-tools"]["env"]["SAL_GATE_ROUTING_V2"] == "1"
    assert "sal_vendor_routing_v2: ON" in o.system_prompt
    assert sal.normalize_variant("off")[0] == "off"


def test_result_is_sim_readable():
    r = sal.RunResult(run_id="w", day="sun", variant="on", ok=True, orders=["ORD-1"], rule_id="RULE-1")
    d = dict(r.__dict__)
    assert d["ok"] and d["orders"] == ["ORD-1"] and d["rule_id"] == "RULE-1"
