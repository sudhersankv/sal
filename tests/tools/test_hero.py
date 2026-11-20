"""Hero week tool outputs are contract-shaped and every emitted event validates."""
import asyncio
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from tools import context, impl

ROOT = Path(__file__).resolve().parents[2]
V = Draft202012Validator(json.loads((ROOT / "contracts/events.schema.json").read_text(encoding="utf-8")))


def _events(tmp):
    return [json.loads(x) for x in (tmp / "test" / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def test_server_lists_every_contract_tool():
    from tools.server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    contract = set(re.findall(r"^\| `([a-z_]+)` \|", (ROOT / "contracts/tools.md").read_text(encoding="utf-8"), re.M))
    assert contract <= names


def test_monday(_offline_fixture_world):
    tmp = _offline_fixture_world
    intake = impl.extract_intake("Civic in bay 2, P0141, VIN 19XFB2F58EE214879, customer promised by 3 PM")
    assert (intake["dtc"], intake["bay"]) == ("P0141", 2)
    car = impl.decode_vin(intake["vin"])
    assert {"year", "make", "model", "trim", "engine_l", "cylinders", "raw_source_url"} <= car.keys()
    part = impl.identify_part(car["year"], car["make"], car["model"], car["engine_l"], dtc="P0141")
    assert part["position"] == "downstream"
    listings = [x for v in ("mission", "bayshore", "partsdepot")
                for x in impl.search_vendor(v, part["oem_part_no"])["listings"]]
    keys = {"vendor_id", "sku", "vendor_part_no", "brand", "desc", "price", "qty_on_hand", "eta_minutes", "core_charge"}
    assert all(keys <= set(x) for x in listings)
    verdicts = {r["sku"]: r["verdict"] for r in impl.match_listings(part["oem_part_no"], listings)["results"]}
    assert verdicts["BPC-DEN-AF14U"] == "different" and verdicts["MAS-DEN-2344B2"] == "same"
    assert impl.get_brand_history("ValuMax", "o2_sensor")["comebacks"] == 2
    rules = impl.get_shop_rules("rules for O2 sensors")
    assert rules["passages"] and "content_id" in rules["passages"][0]
    assert "escalation" in impl.place_counter_order("bayshore", "BPC-VM-O2D14", 1, "RO-1042")
    q = impl.compute_quote(41)
    appr = impl.request_owner_approval("RO-1042", "C-ruiz", [{"desc": "O2 sensor", "price": q["retail"]}], q["retail"])
    assert appr["status"] in ("approved", "declined", "pending")
    order = impl.place_counter_order("mission", "MAS-DEN-2344B2", 1, "RO-1042")
    assert {"order_id", "eta", "total"} <= order.keys() and order["total"] == 41.0
    assert "payment_id" in impl.record_payment("RO-1042", "C-ruiz", q["retail"])
    assert "id" in impl.emit_event({"type": "sal.summary", "summary": "Civic part ordered"})
    evts = _events(tmp)
    for e in evts:
        assert not list(V.iter_errors(e)), e
    types = {e["type"] for e in evts}
    assert {"part.identified", "context.retrieved", "vendors.compared", "escalation", "quote.sent",
            "approval.requested", "approval.received", "order.placed", "payment.recorded", "sal.summary"} <= types
    assert "error" not in types


def test_tuesday_over_cap_needs_verified_owner():
    context.set_context(day="tue")
    assert impl.place_counter_order("mission", "MAS-MC-ALT35", 1, "RO-1050")["escalation"]["rule"] == "R1"
    v = impl.verify_owner("alternator over cap", 260, "RO-1050")
    assert {"inquiry_id", "status", "verified_name", "hosted_url", "method"} <= v.keys()
    out = impl.place_counter_order("mission", "MAS-MC-ALT35", 1, "RO-1050", approval_id=v["inquiry_id"])
    assert "order_id" in out


def test_wednesday_restock_order():
    context.set_context(day="wed")
    plan = impl.plan_restock()
    out = impl.place_shopify_order([{"variant_id": ln["variant_id"], "qty": ln["order_qty"]} for ln in plan["lines"]],
                                   "restock")
    assert {"shopify_order_id", "admin_url", "total"} <= out.keys() and out["total"] == 153.0


def test_sunday_rule_flow():
    context.set_context(day="sun")
    assert impl.recall_facts("Bayshore late starters")["facts"]
    r = impl.propose_rule("Route starters & alternators to Mission", "Route them.",
                          [{"name": "SingleStore", "ref": "purchase_history"}, {"name": "Cognee", "ref": "fact"}])
    assert r["status"] == "pending_owner"
    a = impl.approve_rule(r["rule_id"])
    assert {"senso_content_id", "statsig_gate"} <= a.keys()


def test_friday_statement():
    context.set_context(day="fri")
    st = impl.parse_vendor_statement("tools/samples/bayshore_statement_2026-11.csv")
    assert st["method"] == "csv" and st["vendor_id"] == "bayshore" and len(st["lines"]) == 14
    rec = impl.reconcile_statement("bayshore", st["lines"])
    assert len(rec["missing_core_credits"]) == 2 and rec["total_due"] == 90.0


def test_errors_never_raise():
    assert "error" in impl.place_counter_order("nope", "nope", 1, "RO-1")
    assert "error" in impl.emit_event({"type": "not-a-type", "summary": "x"})
