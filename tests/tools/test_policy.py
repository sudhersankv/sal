import json

import pytest

from tools import policy
from tools.policy import Line, Policy, check_order

O2_VALUMAX = Line("BPC-VM-O2D14", "ValuMax", "o2_sensor", 1, 33.0)
O2_DENSO = Line("MAS-DEN-2344B2", "Denso", "o2_sensor", 1, 41.0)
PADS_VALUMAX = Line("X", "ValuMax", "brake_pads", 1, 30.0)
STARTER = Line("BPC-DEN-STR25", "Denso", "starter", 1, 152.0)
ALT = Line("MAS-MC-ALT35", "Motorcraft", "alternator", 1, 260.0)


@pytest.mark.parametrize("vendor,line,total,routing,approval,expect", [
    ("bayshore", O2_VALUMAX, 33, False, None, "no_buy"),       # R4
    ("mission", O2_DENSO, 41, False, None, None),              # allowed
    ("bayshore", PADS_VALUMAX, 30, False, None, None),         # R4 is sensors only
    ("mission", ALT, 260, False, None, "spend_cap"),           # R1 no approval
    ("mission", ALT, 260, False, "inq_fake", "spend_cap"),     # R1 unverified approval id
    ("mission", ALT, 200, False, None, None),                  # cap is strictly greater-than
    ("bayshore", STARTER, 152, True, None, "routing_gate"),    # gate ON, wrong vendor
    ("mission", STARTER, 152, True, None, None),               # gate ON, routed vendor
    ("bayshore", STARTER, 152, False, None, None),             # gate OFF
])
def test_policy_table(vendor, line, total, routing, approval, expect):
    esc = check_order(vendor, [line], total, approval, Policy(routing_on=routing))
    assert (esc or {}).get("code") == expect


def test_spend_cap_passes_with_verified_owner():
    policy.record_verification({"inquiry_id": "inq_ok", "status": "pending"})
    assert check_order("mission", [ALT], 260, "inq_ok", Policy())["code"] == "spend_cap"
    policy.record_verification({"inquiry_id": "inq_ok", "status": "approved"})
    assert check_order("mission", [ALT], 260, "inq_ok", Policy()) is None


def test_gate_from_variant_env(monkeypatch):
    monkeypatch.setenv("SAL_VARIANT", "on")
    assert policy.current().routing_on
    monkeypatch.setenv("SAL_VARIANT", "off")
    assert not policy.current().routing_on


def test_guard_emits_escalation(tmp_path):
    out = policy.guard("bayshore", [O2_VALUMAX], 33, ro_id="RO-1042")
    assert out["escalation"]["rule"] == "R4"
    evts = [json.loads(x) for x in (tmp_path / "test" / "events.jsonl").read_text().splitlines()]
    assert evts[-1]["type"] == "escalation"
