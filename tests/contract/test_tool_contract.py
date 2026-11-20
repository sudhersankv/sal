"""Every tool named in contracts/tools.md must be registered by tools/server.py once it exists."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = sorted(set(re.findall(r"^\| `([a-z_]+)` \|", (ROOT / "contracts/tools.md").read_text(encoding="utf-8"), re.M)))


def test_contract_lists_tools():
    assert {"decode_vin", "place_counter_order", "parse_vendor_statement"} <= set(TOOLS)


@pytest.mark.skipif(not (ROOT / "tools/server.py").exists(), reason="tools/server.py not written yet")
async def test_server_registers_every_tool():
    from tools.server import mcp
    names = {t.name for t in await mcp.list_tools()}
    assert set(TOOLS) - names == set(), f"missing: {set(TOOLS) - names}"
