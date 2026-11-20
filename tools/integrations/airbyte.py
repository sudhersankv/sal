"""Airbyte context layer over the shop sheets (D-007): bookings + vendor price sheets.

Documented headless path (docs.airbyte.com/platform/airbyte-mcp, /platform/context-layer):
hosted MCP at https://mcp.airbyte.com/mcp (Streamable HTTP) with headers `Client-Id`, `Client-Secret`,
optional `X-Airbyte-Workspace-Id`. Search tool: `execute_external_search_query` (needs agent connectors +
search enabled + backfill). No REST search endpoint / SDK search function is documented.
The tool's input schema is not documented, so we read it from list_tools and fill the first string field
that looks like a query. Any failure → local CSVs in seed/shop_sheets/*.csv (source="csv").
REST token (for future use): POST https://api.airbyte.com/v1/applications/token.
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
import threading

from ._common import SEED, cache_get, cache_put, env, has, key_for, log, replay, safe_exc

SERVICE = "airbyte"
SHEETS = SEED / "shop_sheets"
MCP_URL = "https://mcp.airbyte.com/mcp"
SEARCH_TOOL = "execute_external_search_query"
_TOK = re.compile(r"[a-z0-9]+")


def available() -> bool:
    return has("AIRBYTE_CLIENT_ID", "AIRBYTE_CLIENT_SECRET")


def list_streams() -> list[str]:
    if not SHEETS.exists():
        return []
    return sorted(p.stem for p in SHEETS.glob("*.csv"))


# ---------------------------------------------------------------- fallback
def _csv_records(stream: str | None) -> list[dict]:
    out = []
    for name in list_streams():
        if stream and name != stream:
            continue
        with (SHEETS / f"{name}.csv").open(encoding="utf-8-sig", newline="") as f:
            for i, row in enumerate(csv.DictReader(f)):
                fields = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                rid = fields.get("id") or fields.get("booking_id") or fields.get("sku") or f"{name}-{i + 1}"
                out.append({"stream": name, "id": rid, "fields": fields})
    return out


def _csv_search(query: str, stream: str | None, limit: int, recs: list[dict] | None = None) -> list[dict]:
    recs = _csv_records(stream) if recs is None else recs
    q = set(_TOK.findall((query or "").lower()))
    if not q or q <= {"all", "list", "everything", "bookings", "booking", "price", "prices", "sheet", "sheets"}:
        return recs[:limit]
    scored = []
    for r in recs:
        toks = set(_TOK.findall(" ".join(r["fields"].values()).lower()))
        s = len(q & toks)
        if s:
            scored.append((s, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:limit]]


# ---------------------------------------------------------------- live (MCP)
async def _mcp_search(query: str, stream: str | None, limit: int):
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Client-Id": env("AIRBYTE_CLIENT_ID"), "Client-Secret": env("AIRBYTE_CLIENT_SECRET")}
    if env("AIRBYTE_WORKSPACE_ID"):
        headers["X-Airbyte-Workspace-Id"] = env("AIRBYTE_WORKSPACE_ID")
    async with httpx2.AsyncClient(headers=headers, timeout=60) as http:
        async with streamable_http_client(MCP_URL, http_client=http) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                tools = (await s.list_tools()).tools
                tool = next((t for t in tools if t.name == SEARCH_TOOL), None)
                if tool is None:
                    raise RuntimeError(f"{SEARCH_TOOL} not offered; tools={[t.name for t in tools][:10]}")
                props = (tool.inputSchema or {}).get("properties", {})
                args: dict = {}
                qkey = next((k for k in props if k in ("query", "q", "search_query", "text")), None)
                qkey = qkey or next((k for k, v in props.items() if v.get("type") == "string"), "query")
                args[qkey] = f"{stream}: {query}" if stream else query
                for k in ("limit", "top_k", "max_results"):
                    if k in props:
                        args[k] = limit
                res = await s.call_tool(SEARCH_TOOL, args)
                if getattr(res, "isError", False):
                    raise RuntimeError(str(res.content)[:200])
                return res


def _run(coro, timeout=60):
    box: dict = {}

    def target():
        try:
            box["v"] = asyncio.run(asyncio.wait_for(coro, timeout))
        except BaseException as e:  # noqa: BLE001
            box["e"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout + 5)
    if "e" in box:
        raise box["e"]
    if "v" not in box:
        raise TimeoutError("airbyte mcp timed out")
    return box["v"]


def _records_from_mcp(res, stream: str | None) -> list[dict]:
    payload = getattr(res, "structuredContent", None)
    if payload is None:
        texts = [getattr(c, "text", "") for c in (res.content or [])]
        blob = "\n".join(t for t in texts if t)
        try:
            payload = json.loads(blob)
        except Exception:
            payload = {"text": blob}
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("records") or payload.get("results") or payload.get("data") or [payload]
    out = []
    for i, r in enumerate(rows if isinstance(rows, list) else [rows]):
        fields = r if isinstance(r, dict) else {"text": str(r)}
        out.append({"stream": fields.get("stream") or stream or "unknown", "id": str(fields.get("id", i + 1)), "fields": fields})
    return out


def search_shop_data(query: str, stream: str | None = None, limit: int = 20) -> dict:
    k = key_for("search", query, stream, limit)
    if replay():
        hit = cache_get(SERVICE, k)
        if hit:
            return hit
    if available():
        try:
            res = _run(_mcp_search(query, stream, limit))
            recs = _records_from_mcp(res, stream)
            out = {"records": recs[:limit], "source": "airbyte"}
            cache_put(SERVICE, k, out)
            return out
        except Exception as e:
            log(f"[airbyte] mcp search failed → csv: {safe_exc(e)}")
    from tools.integrations import airbyte_oss
    if airbyte_oss.synced():
        return {"records": _csv_search(query, stream, limit, airbyte_oss.records(stream)), "source": "airbyte-oss"}
    return {"records": _csv_search(query, stream, limit), "source": "csv"}
