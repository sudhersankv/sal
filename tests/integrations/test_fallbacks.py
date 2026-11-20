"""Fallback paths only — no network. Every key is blanked and the cache root is redirected to tmp."""

from __future__ import annotations

import importlib
import json

import pytest

KEYS = [
    "SIE_API_KEY", "SENSO_API_KEY", "PERSONA_API_KEY", "PERSONA_TEMPLATE_ID", "AIRBYTE_CLIENT_ID",
    "AIRBYTE_CLIENT_SECRET", "SHOPIFY_SHOP", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET", "COGNEE_URL",
    "COGNEE_API_KEY", "STATSIG_SERVER_SECRET", "STATSIG_CONSOLE_API_KEY", "AMPLITUDE_AI_API_KEY",
    "SAL_GATE_ROUTING", "SAL_POLICY_STRATEGY", "DEMO_MODE",
]


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    for k in KEYS:
        monkeypatch.setenv(k, "")
    from tools.integrations import _common

    monkeypatch.setattr(_common, "CACHE_ROOT", tmp_path / "cache")

    def no_net(*a, **k):
        raise AssertionError("network call in offline test")

    import httpx

    monkeypatch.setattr(httpx, "get", no_net)
    monkeypatch.setattr(httpx, "post", no_net)
    yield tmp_path


def test_sie_embed_fallback_deterministic():
    from tools.integrations import sie

    a = sie.embed(["Denso 234-4012 O2 sensor upstream", "Denso 234-4012 O2 sensor upstream", "brake pads"])
    assert a["source"] == "fallback" and a["dim"] == 256
    v = a["vectors"]
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))  # noqa: E731
    assert dot(v[0], v[1]) == pytest.approx(1.0)
    assert dot(v[0], v[2]) < 0.9
    assert sie.embed(["x"])["vectors"] == sie.embed(["x"])["vectors"]


def test_sie_rerank_fallback_orders_by_overlap():
    from tools.integrations import sie

    r = sie.rerank("upstream O2 sensor Civic", ["brake rotor", "Denso upstream O2 sensor", "wiper blade"])
    assert r["results"][0]["index"] == 1
    assert [x["rank"] for x in r["results"]] == [0, 1, 2]


def test_sie_extract_entities_regex():
    from tools.integrations import sie

    text = "Bay 3: 2014 Honda Civic VIN 19XFB2F59EE000000 throwing P0141, customer promised by 2pm"
    r = sie.extract_entities(text, ["vin", "dtc", "bay", "vehicle", "promise_time"])
    got = {e["label"]: e["text"] for e in r["entities"]}
    assert r["source"] == "fallback"
    assert got["vin"] == "19XFB2F59EE000000"
    assert got["dtc"] == "P0141"
    assert got["bay"] == "3"
    assert got["vehicle"].startswith("2014 Honda Civic")
    assert got["promise_time"] == "2pm"


def test_sie_extract_document_csv_fallback(tmp_path):
    from tools.integrations import sie

    p = tmp_path / "stmt.csv"
    p.write_text("Date,Invoice_No,SKU,Qty,Amount\n2026-11-02,INV-1,BAY-123,1,89.50\n", encoding="utf-8")
    r = sie.extract_document(p, {"type": "object"})
    assert r["method"] == "csv"
    assert r["data"]["lines"][0]["invoice_no"] == "INV-1"


def test_sie_llm_and_ocr_return_error_not_raise():
    from tools.integrations import sie

    assert "error" in sie.llm([{"role": "user", "content": "hi"}])
    assert "error" in sie.ocr_image(b"\x89PNG fake")
    assert "skipped" in json.dumps(sie.warm())


def test_senso_local_search(monkeypatch, tmp_path):
    from tools.integrations import senso

    d = tmp_path / "docs"
    d.mkdir()
    (d / "no-buy-list.md").write_text("# No-buy list\n\nNever buy ValuMax O2 sensors.\n", encoding="utf-8")
    (d / "markup.md").write_text("# Markup matrix\n\nUnder $50: 100%.\n", encoding="utf-8")
    monkeypatch.setattr(senso, "DOCS_DIR", d)
    r = senso.search("rules for O2 sensors")
    assert r["source"] == "fallback"
    assert r["passages"][0]["content_id"] == "local:no-buy-list"
    added = senso.add_doc("Route starters to Mission", "Starters go to Mission Auto Supply.")
    assert added["content_id"].startswith("local:")
    assert senso.search_context("starters Mission")["passages"][0]["title"] == "Route starters to Mission"


def test_persona_simulated_flow():
    from tools.integrations import persona

    r = persona.verify_owner("Alternator $260 > cap", 260.0, "RO-1001")
    assert r["method"] == "simulated" and r["status"] == "pending" and r["inquiry_id"].startswith("inq_sim_")
    assert persona.approve(r["inquiry_id"])["status"] == "approved"
    assert persona.get_status(r["inquiry_id"])["status"] == "approved"


def test_airbyte_csv_fallback(monkeypatch, tmp_path):
    from tools.integrations import airbyte, airbyte_oss

    monkeypatch.setattr(airbyte_oss, "OUT", tmp_path / "no-sync")

    d = tmp_path / "sheets"
    d.mkdir()
    (d / "bookings.csv").write_text("booking_id,date,service_code,vehicle\nB1,2026-11-19,OIL,2016 Ford F-150\nB2,2026-11-20,BRAKE,2018 Toyota Camry\n", encoding="utf-8")
    (d / "price_sheets.csv").write_text("sku,vendor_id,price\nPD-1,partsdepot,4.99\n", encoding="utf-8")
    monkeypatch.setattr(airbyte, "SHEETS", d)
    assert airbyte.list_streams() == ["bookings", "price_sheets"]
    r = airbyte.search_shop_data("camry brake", "bookings")
    assert r["source"] == "csv" and r["records"][0]["id"] == "B2"
    assert len(airbyte.search_shop_data("all")["records"]) == 3


def test_shopify_fallback_errors_cleanly_when_mock_down():
    from tools.integrations import shopify

    assert shopify.get_token() is None
    r = shopify.place_order([{"variant_id": "gid://shopify/ProductVariant/1", "qty": 2}], "test")
    assert r.get("source") == "fallback"  # mock unreachable → error dict, never raises


def test_cognee_jsonl_fallback():
    from tools.integrations import cognee

    assert cognee.remember("Bayshore late on 3 of last 8 starter deliveries", ["bayshore", "late"])["ok"]
    cognee.remember("ValuMax O2 sensor comeback on RO-0977", ["valumax"])
    r = cognee.recall("Bayshore late starter")
    assert r["source"] == "fallback" and "Bayshore" in r["facts"][0]["text"]


def test_statsig_overrides(monkeypatch):
    from tools.integrations import statsig_client

    assert statsig_client.check_gate() is False
    assert statsig_client.get_config()["strategy"] == "rules_aware"
    monkeypatch.setenv("SAL_GATE_ROUTING", "on")
    monkeypatch.setenv("SAL_POLICY_STRATEGY", "cheapest")
    v = statsig_client.variant()
    assert v == {"gate_routing_v2": True, "strategy": "cheapest", "source": "override"}
    assert statsig_client.ensure_console_objects()["skipped"]


def test_amplitude_fallback(offline):
    from tools.integrations import amplitude

    assert amplitude.track("sal_order_placed", {"variant": "on"}, session_id="run-1")["source"] == "fallback"
    lines = (offline / "cache" / "amplitude" / "events.jsonl").read_text().splitlines()
    assert json.loads(lines[-1])["event_properties"]["run_id"] == "run-1"


def test_nhtsa_reads_seed_cache(monkeypatch, tmp_path):
    from tools.integrations import nhtsa

    monkeypatch.setattr(nhtsa, "SEED_CACHE", tmp_path)
    vin = "19XFB2F59EE000000"
    (tmp_path / f"vin_{vin}.json").write_text(json.dumps({"Results": [{
        "ModelYear": "2014", "Make": "HONDA", "Model": "Civic", "Trim": "LX", "DisplacementL": "1.8", "EngineCylinders": "4",
    }]}))
    r = nhtsa.decode_vin(vin)
    assert (r["year"], r["make"], r["engine_l"], r["cylinders"], r["source"]) == (2014, "Honda", 1.8, 4, "seed_cache")
    (tmp_path / "complaints_honda_civic_2014.json").write_text(json.dumps({"results": [
        {"odiNumber": 1, "components": "ENGINE", "summary": "oxygen sensor failed"},
        {"odiNumber": 2, "components": "BRAKES", "summary": "pads"},
    ]}))
    c = nhtsa.complaints("Honda", "Civic", 2014, "oxygen")
    assert (c["total"], c["matching"], c["top"][0]["odi"]) == (2, 1, 1)


def test_modules_import_cleanly():
    for m in ["sie", "senso", "persona", "airbyte", "shopify", "cognee", "statsig_client", "amplitude", "nhtsa", "smoke"]:
        importlib.import_module(f"tools.integrations.{m}")


def test_sie_reasoning_strip_and_json_parse():
    from tools.integrations import sie

    assert sie._strip_reasoning("<think>hmm</think>\n{\"a\": 1}") == '{"a": 1}'
    assert sie._strip_reasoning("half</think>ok") == "ok"
    assert sie._parse_json('```json\n{"lines": [1]}\n```') == {"lines": [1]}


def test_sie_parse_statement_csv_offline():
    from tools.integrations import sie

    r = sie.parse_statement("seed/statements/bayshore_2026-11.csv")
    assert r["method"] == "csv" and len(r["lines"]) == 25
    zero_core = {ln["sku"] for ln in r["lines"] if ln["core_credit"] == 0 and ("STARTER" in ln["desc"] or "ALTERNATOR" in ln["desc"])}
    assert zero_core == {"BSP101591", "BSP104218"}
    assert r["total"] == 1494.30
