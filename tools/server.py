"""sal-tools MCP server (stdio): `python -m tools.server`.

Every tool in contracts/tools.md. Implementations live in tools/impl.py (dict in/out, never raise).
`approve_rule` is registered (sim/owner UI use it) but Sal's agent must exclude it via
disallowed_tools=["mcp__sal-tools__approve_rule"].
"""
from __future__ import annotations

import logging
import sys

from mcp.server.mcpserver import MCPServer

from tools import impl

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)  # stdout is the MCP channel

mcp = MCPServer(
    "sal-tools",
    instructions=("Sal's parts-desk tools for Mission Street Auto. Every decision-relevant tool auto-emits its "
                  "timeline event. Errors come back as {'error': {...}}; policy refusals as {'escalation': {...}} "
                  "— never work around an escalation."),
)

TOOLS = [
    impl.decode_vin, impl.get_complaints, impl.get_shop_rules, impl.identify_part, impl.search_vendor,
    impl.match_listings, impl.get_brand_history, impl.compute_quote, impl.request_owner_approval,
    impl.place_counter_order, impl.place_shopify_order, impl.record_payment, impl.get_inventory,
    impl.get_bookings, impl.plan_restock, impl.get_vendor_history, impl.propose_rule, impl.approve_rule,
    impl.remember_fact, impl.recall_facts, impl.emit_event, impl.extract_intake, impl.parse_vendor_statement,
    impl.reconcile_statement, impl.verify_owner, impl.search_shop_data,
]

for _fn in TOOLS:
    mcp.tool(structured_output=False)(_fn)
    globals()[_fn.__name__] = _fn  # `from tools.server import approve_rule` works for sim/ui


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
