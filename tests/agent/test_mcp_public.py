"""Public Sal MCP over stdio with a real MCP client (no LLM calls)."""
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent import mcp_public

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {"ask_sal", "get_today", "list_waiting", "decide", "why", "get_inventory", "get_orders",
            "get_vendor_scorecards", "send_bill"}


def _json(res):
    return json.loads(res.content[0].text)


async def test_stdio_tools_and_resources():
    params = StdioServerParameters(command=sys.executable, args=["-m", "agent.mcp_public"], cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            assert names == EXPECTED, names
            assert not any(n.startswith("place_") or n == "approve_rule" for n in names)
            w = _json(await s.call_tool("list_waiting", {}))
            assert "summary" in w and isinstance(w["waiting"], list)
            y = _json(await s.call_tool("why", {"ref": "no-such-ref-xyz"}))
            assert y["lines"] == [] and "Nothing on record" in y["summary"]
            inv = _json(await s.call_tool("get_inventory", {"filter": "all"}))
            assert inv["items"], inv
            uris = {str(r.uri) for r in (await s.list_resources()).resources}
            assert {"sal://today", "sal://inventory", "sal://activity"} <= uris


async def test_decide_refuses_over_cap_without_persona(monkeypatch):
    monkeypatch.setattr(mcp_public.chat, "action_index", lambda cid="*": {
        "act_x": {"action_id": "act_x", "kind": "approval", "status": "waiting_owner",
                  "title": "Alternator $260 at Mission", "chat_id": "123", "refs": {"ro_id": "RO-1047"}}})
    monkeypatch.setattr(mcp_public, "_persona_link", lambda title, ro: {"inquiry_id": "inq_1", "status": "pending",
                                                                       "hosted_url": "https://withpersona.com/x"})
    called = []
    monkeypatch.setattr(mcp_public, "_chat", lambda *a: called.append(a))
    out = await mcp_public.decide("act_x", True)
    assert out["status"] == "pending" and out["persona_url"].startswith("https://withpersona.com") and not called
    assert (await mcp_public.decide("nope", True))["status"] == "not_found"


def test_http_refuses_without_token(monkeypatch):
    monkeypatch.delenv("SAL_MCP_TOKEN", raising=False)
    monkeypatch.setattr(mcp_public.core, "load_env", lambda: None)
    assert mcp_public.main(["--http"]) == 2


def test_http_bearer_auth():
    from starlette.testclient import TestClient

    c = TestClient(mcp_public.http_app("s3cret"))
    assert c.post("/mcp", json={}).status_code == 401
    assert c.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401
