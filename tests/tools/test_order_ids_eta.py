"""Regressions from live chat runs: (1) search_vendor -> place_counter_order must round-trip whatever identifier
search returned; (2) ETAs come from the simulated shop clock, never the mock vendor's own clock."""
import json
from datetime import datetime, timedelta

import pytest

from tools import context, impl
from tools import fixtures as fx

ALT_OEM = "FL3T-10300-AA"  # TUE F-150 alternator (fixture world)
O2_OEM = fx.HERO_OEM_DOWNSTREAM  # MON hero


def _listings(oem):
    return [x for v in ("mission", "bayshore", "partsdepot") for x in impl.search_vendor(v, oem)["listings"]]


@pytest.mark.parametrize("oem,day", [(ALT_OEM, "tue"), (O2_OEM, "mon")])
@pytest.mark.parametrize("ident", ["sku", "vendor_part_no"])
def test_search_then_place_round_trips(oem, day, ident):
    context.set_context(day=day)
    listings = [x for x in _listings(oem) if x["oem_part_no"] == oem]
    assert len(listings) >= 2
    owner = impl.verify_owner("over-cap part for a lifted car", 300, "RO-1050")["inquiry_id"]
    for x in listings:
        out = impl.place_counter_order(x["vendor_id"], x[ident], 1, "RO-1050", approval_id=owner)
        assert "error" not in out, (x, out)
        if "escalation" in out:  # only legitimate policy refusals (R4 ValuMax sensors)
            assert out["escalation"]["rule"] == "R4" and x["brand"] == "ValuMax"
        else:
            assert out["total"] == x["price"]


def test_place_accepts_unambiguous_oem_and_explains_ambiguous():
    context.set_context(day="tue")
    owner = impl.verify_owner("alternator", 300, "RO-1050")["inquiry_id"]
    assert "order_id" in impl.place_counter_order("mission", ALT_OEM, 1, "RO-1050", approval_id=owner)
    amb = impl.place_counter_order("bayshore", O2_OEM, 1, "RO-1042")
    assert amb["error"]["code"] == "ambiguous_part" and "BPC-" in amb["error"]["message"]
    assert impl.place_counter_order("mission", "nope-123", 1, "RO-1")["error"]["code"] == "unknown_sku"


@pytest.mark.parametrize("day", ["wed", "fri"])
def test_online_restock_eta_is_two_days_from_sim_clock(day):
    context.set_context(day=day)
    out = impl.place_shopify_order([{"sku": "OF-CIVIC", "qty": 2}, {"sku": "BRK-CLN", "qty": 1}], "restock")
    assert datetime.fromisoformat(out["eta"]) == context.now() + timedelta(minutes=2880)
    assert datetime.fromisoformat(out["eta"]) > context.now()


def test_counter_eta_from_sim_clock():
    context.set_context(day="mon")
    out = impl.place_counter_order("mission", "MAS-DEN-2344B2", 1, "RO-1042")
    assert out["eta"] == "2026-11-16T10:20:00-08:00"


def test_mock_vendor_without_sim_ts_uses_run_clock(_offline_fixture_world, monkeypatch):
    from vendors import catalog
    monkeypatch.delenv("SAL_SIM_TS", raising=False)
    monkeypatch.delenv("SAL_RUN_ID", raising=False)
    run = _offline_fixture_world / "wkrun"
    run.mkdir()
    (run / "events.jsonl").write_text(json.dumps({"ts": "2026-11-18T07:31:00-08:00"}) + "\n", encoding="utf-8")
    order = catalog.place_many("partsdepot", [("OF-CIVIC", 1)], None, run_id="wkrun")
    assert order["eta"] == "2026-11-20T07:31:00-08:00"
    # no run id at all: newest run log wins
    order = catalog.place_many("partsdepot", [("OF-CIVIC", 1)], None)
    assert order["eta"] == "2026-11-20T07:31:00-08:00"
