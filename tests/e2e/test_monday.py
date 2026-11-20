"""Golden path (SPEC §14): run Monday through Sal against stub tools; assert required event types, no errors.

Live Claude call, so skipped without ANTHROPIC_API_KEY. Uses tools/server.py when present (set
SAL_E2E_TOOLS=fake to force tests/e2e/fake_tools.py). Not part of `tasks.py check` (it ignores tests/e2e).
"""
import json
import os
import uuid
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

pytestmark = pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")

# contracts/demo_script.md MON, minus order.delivered (the sim advances the clock for that one).
MON_REQUIRED = {
    "repair_order.created", "part.identified", "context.retrieved", "vendors.compared", "part.rejected",
    "part.chosen", "quote.sent", "approval.requested", "approval.received", "order.placed",
    "payment.recorded", "sal.summary",
}


def _tools_module() -> str:
    if os.getenv("SAL_E2E_TOOLS") == "fake" or not (ROOT / "tools/server.py").exists():
        return "tests.e2e.fake_tools"
    return "tools.server"


def test_monday_golden_path(monkeypatch):
    from agent import sal

    monkeypatch.setenv("SAL_TOOLS_MODULE", _tools_module())
    monkeypatch.setenv("SAL_ANALYTICS", os.getenv("SAL_ANALYTICS", "off"))
    run_id = f"e2e-mon-{uuid.uuid4().hex[:6]}"
    res = sal.run_day("mon", sal.DEFAULT_TRIGGERS["mon"], "off", run_id)

    path = ROOT / "runs" / run_id / "events.jsonl"
    assert path.exists(), f"no events written for {run_id}; result: {res.to_json()}"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    types = {e["type"] for e in events}

    assert res.ok, res.error
    assert "approve_rule" not in res.tool_calls
    assert MON_REQUIRED - types == set(), f"missing {MON_REQUIRED - types}; got {sorted(types)}"
    assert not [e for e in events if e["type"] == "error"]
    schema = json.loads((ROOT / "contracts/events.schema.json").read_text(encoding="utf-8"))
    for e in events:
        jsonschema.validate(e, schema)
    chosen = [e for e in events if e["type"] == "part.chosen"]
    assert chosen and all(e.get("sources") for e in chosen), "part.chosen must cite sources"
