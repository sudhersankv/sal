# Talk to Sal from any agent (MCP)

Sal has a public MCP server: a front door for your own agent (Claude, ChatGPT, Muse, Instinct, …). It reaches the
**same Sal** you text on Telegram: same memory, same action list, same shop rules and approvals.

It's separate from the internal `sal-tools` server and never exposes raw ordering tools. Spend only happens
through Sal, inside the owner's rules. **An agent can't approve over-cap spend:** `decide` sends back a Persona
link for the owner to verify.

| Tool | What it does |
|---|---|
| `ask_sal(message, caller?)` | Text Sal in plain language ("are we low for the Civics?", "go get them", "Civic bay 2 P0141 VIN … promised 3pm"). Each `caller` gets its own thread with memory. |
| `get_today()` | Brief: waiting on owner, arriving today, late orders, low stock, spend this week |
| `list_waiting()` | Items waiting on the owner, across Telegram, the dashboard and MCP |
| `decide(action_id, approve, note?)` | Approve or decline, like the Telegram buttons. Over-cap returns `status: pending` and a `persona_url` |
| `why(ref)` | Reasons and sources for an order id, RO id or action id |
| `get_inventory(filter)` · `get_orders(status)` · `get_vendor_scorecards(days)` | Read-only views |

Resources: `sal://today`, `sal://inventory`, `sal://activity`.

## Run it
```bash
# stdio (local agents)
uv run python -m agent.mcp_public

# Streamable HTTP at /mcp. Bearer auth is required; the server refuses to start without SAL_MCP_TOKEN
SAL_MCP_TOKEN=<long-random-token> uv run python -m agent.mcp_public --http --port 8103
# expose it publicly with any tunnel, e.g.  cloudflared tunnel --url http://localhost:8103
```
Every message shows up in the dashboard's Activity & Trace as `chat.message` with `data.channel = "mcp"`.

## Claude Code
```bash
# remote (HTTP)
claude mcp add --transport http sal https://<your-host>/mcp --header "Authorization: Bearer $SAL_MCP_TOKEN"
# local (stdio), run from the repo root
claude mcp add sal -- uv run --directory /path/to/sal python -m agent.mcp_public
```

## Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "sal": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/sal", "python", "-m", "agent.mcp_public"]
    }
  }
}
```
For the remote server, add it as a custom connector with URL `https://<your-host>/mcp` and the bearer token,
or bridge it: `"command": "npx", "args": ["-y", "mcp-remote", "https://<your-host>/mcp", "--header", "Authorization: Bearer <token>"]`.

## ChatGPT / OpenAI (remote MCP)
OpenAI Agents SDK (Python):
```python
from agents import Agent
from agents.mcp import MCPServerStreamableHttp

sal = MCPServerStreamableHttp(params={"url": "https://<your-host>/mcp",
                                      "headers": {"Authorization": "Bearer <token>"}})
agent = Agent(name="my-assistant", mcp_servers=[sal])
```
Responses API tool entry:
```json
{"type": "mcp", "server_label": "sal", "server_url": "https://<your-host>/mcp",
 "headers": {"Authorization": "Bearer <token>"}, "require_approval": "never"}
```
In ChatGPT (developer mode / connectors), add a custom MCP connector with the same URL and bearer token.

## Any MCP client (Python)
```python
import httpx2  # ships with mcp 2.x
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with httpx2.AsyncClient(headers={"Authorization": "Bearer <token>"}, timeout=600) as hc:
  async with streamable_http_client("https://<your-host>/mcp", http_client=hc) as (read, write, *_):
    async with ClientSession(read, write) as s:
        await s.initialize()
        r = await s.call_tool("ask_sal", {"message": "are we low for the Civics next week?", "caller": "my-agent"})
```

## `.mcp.json` (project-scoped, Claude Code and others)
```json
{
  "mcpServers": {
    "sal": { "command": "uv", "args": ["run", "python", "-m", "agent.mcp_public"] },
    "sal-remote": {
      "type": "http",
      "url": "https://<your-host>/mcp",
      "headers": { "Authorization": "Bearer ${SAL_MCP_TOKEN}" }
    }
  }
}
```

## Sending a bill or photo (`send_bill`)

Agents can hand Sal a vendor bill, invoice or statement the same way staff send one on Telegram:

```json
{"tool": "send_bill", "arguments": {"filename": "bayshore_2026-11.pdf", "url": "https://github.com/sudhersankv/sal/raw/main/seed/statements/bayshore_2026-11.pdf", "note": "Bayshore November statement"}}
```

Or pass the bytes as `file_base64`. Accepted: .pdf .png .jpg .jpeg .webp .csv (max 15 MB). Sal parses it (SIE docling / OCR), reconciles it against purchase history in SingleStore, and replies with what's off (e.g. missing core credits) plus a drafted dispute. It never sends the dispute.
