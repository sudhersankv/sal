"""ui/server smoke tests (T5)."""
import json

import pytest
from fastapi.testclient import TestClient

from ui.server import app as app_mod


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "RUNS", tmp_path)
    monkeypatch.setattr(app_mod, "_events", [])
    monkeypatch.setattr(app_mod, "_seen", set())
    monkeypatch.setattr(app_mod, "_logged", {})
    monkeypatch.setattr(app_mod, "SIM_URL", "http://127.0.0.1:9")  # nothing listens
    return TestClient(app_mod.app)


EV = {"id": "evt_t1", "run_id": "t", "ts": "2026-11-16T09:12:00-08:00", "day": "mon",
      "type": "order.placed", "actor": "sal", "summary": "x", "money": {"wholesale": 41, "retail": 82}}


def test_post_event_validates_and_appends(client, tmp_path):
    r = client.post("/events", json=EV)
    assert r.status_code == 200 and r.json()["ok"]
    line = (tmp_path / "t/events.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(line)["id"] == "evt_t1"
    assert client.get("/state").json()["meters"]["margin_pct"] == 50.0


def test_post_event_rejects_bad(client):
    r = client.post("/events", json={"id": "nope", "type": "zzz"})
    assert r.status_code == 422 and r.json()["errors"]


def test_replay_fixture(client):
    r = client.get("/replay")
    assert r.status_code == 200
    types = {e["type"] for e in r.json()["events"]}
    assert {"repair_order.created", "order.placed", "escalation", "rule.approved"} <= types
    m = client.get("/state", params={"replay": "ui/fixtures/sample_week.jsonl"}).json()["meters"]
    assert m["orders"] == 3 and m["variant"] == "routing_v2"


def test_replay_path_escape_blocked(client):
    assert client.get("/replay", params={"path": "../secret.jsonl"}).status_code == 400


def test_sim_proxy_tolerates_down(client):
    r = client.post("/sim/next", json={})
    assert r.status_code == 503 and r.json()["offline"]


def test_no_duplicate_lines_when_producer_wrote_first(client, tmp_path):
    (tmp_path / "t").mkdir()
    (tmp_path / "t/events.jsonl").write_text(json.dumps(EV) + "\n", encoding="utf-8")
    client.post("/events", json=EV)
    client.post("/events", json=EV)
    assert len((tmp_path / "t/events.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert len(client.get("/events").json()) == 1
