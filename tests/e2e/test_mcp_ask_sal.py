"""ask_sal through the public MCP (stdio) against the real chat brain + tools. Needs ANTHROPIC_API_KEY."""
import json
import os
import sys
import uuid
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

pytestmark = pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set")


async def test_ask_sal_list_waiting_why():
    caller = f"e2e-{uuid.uuid4().hex[:6]}"
    params = StdioServerParameters(command=sys.executable, args=["-m", "agent.mcp_public"], cwd=str(ROOT),
                                   env={**os.environ, "SAL_ANALYTICS": "off"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            r = json.loads((await s.call_tool("ask_sal", {"message": "are we low on anything for next week?",
                                                          "caller": caller}, read_timeout_seconds=600)).content[0].text)
            assert r["reply"] and not r["error"], r
            assert "run" not in r["reply"].lower().split()  # no run ids / internals
            w = json.loads((await s.call_tool("list_waiting", {})).content[0].text)
            assert isinstance(w["waiting"], list)
            y = json.loads((await s.call_tool("why", {"ref": "RO-1042"})).content[0].text)
            assert "summary" in y
    log = ROOT / "runs" / "chat" / f"mcp-{caller}.jsonl"
    assert log.exists() and len(log.read_text(encoding="utf-8").splitlines()) == 2
