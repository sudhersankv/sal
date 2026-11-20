"""Owner-app API (D-010): seeds an empty sqlite DB and serves populated pages, like Fly does."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("ui_api")
    mp.setenv("DB_BACKEND", "sqlite")
    mp.setenv("SAL_SQLITE_PATH", str(tmp / "sal.db"))
    mp.setenv("DEMO_MODE", "replay")
    mp.setenv("UI_SKIP_SEED", "1")
    from db import client as dbc
    dbc._DB = None
    from ui.server import api
    mp.setattr(api, "RUNS", tmp / "runs")  # only the fixture as event source
    mp.setattr(api, "DEMO_LOG", tmp / "no-demo.jsonl")
    api._cache["key"] = None
    api.ensure_seeded(background=False)
    from ui.server.app import app
    yield TestClient(app)
    dbc._DB = None
    mp.undo()


def test_seeded_pages_populated(client):
    assert len(client.get("/api/inventory").json()["items"]) > 10
    assert len(client.get("/api/orders").json()["orders"]) > 50
    jobs = client.get("/api/jobs").json()["jobs"]
    assert any(j["ro_id"] == "RO-1042" and j["source"] == "sal" for j in jobs)
    v = client.get("/api/vendors").json()
    assert {x["vendor_id"] for x in v["vendors"]} >= {"mission", "bayshore"}
    assert any(r["rule_id"] == "R8" for r in v["rules"])


def test_activity_and_trace(client):
    a = client.get("/api/activity").json()
    assert a["threads"] and a["actions"]
    assert any(x["status"] == "waiting_owner" for x in a["actions"])
    t = client.get("/api/trace", params={"q": "RO-1042"}).json()["events"]
    assert t and all("RO-1042" in str(e) for e in t)
    d = client.get("/api/jobs/RO-1042").json()
    assert d["listings"] and d["decisions"]


def test_home_and_integrations(client):
    h = client.get("/api/home").json()
    assert h["money"]["spend"] > 0 and h["actions"]
    names = [i["name"] for i in client.get("/api/integrations").json()["integrations"]]
    assert "SingleStore" in names and "Persona" in names


def test_chat_offline_is_graceful(client):
    r = client.post("/chat", json={"chat_id": "ui", "text": "hi"})
    assert r.status_code in (200, 503)
