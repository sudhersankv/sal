# tools/integrations — sponsor/service adapters (owner: `integrations`)

Thin, **sync**, never-raising adapters that `tools/` (the sal-tools MCP server) calls.
Contracts: `contracts/tools.md`. Model routing: D-002 (every non-agent model call → SIE).

## Rules every module follows

- `available() -> bool` — the required env keys are present (does **not** call the network).
- Real implementation when available, **deterministic fallback** otherwise or on any error/timeout.
- **Never raises.** Errors come back as `{"error": {"code": str, "message": str}}` (same shape as the tool contract).
  Most functions prefer to fall back instead of erroring; every dict result carries `"source"` (`"live" | "cache" | "fallback"`).
- Every live response is cached at `runs/cache/<service>/<sha256(input)>.json`. If a live call fails and a cached
  entry exists, the cache is returned (`source="cache"`). `DEMO_MODE=replay` → cache first, network never.
- Env is loaded with `python-dotenv` from the repo root `.env` (via `tools.integrations._common`). Secrets are never logged.

```python
from tools.integrations import sie, senso, persona, airbyte, shopify, cognee, statsig_client, amplitude, nhtsa
```

## sie.py — Superlinked SIE (all non-agent model calls)

Env: `SIE_API_KEY`, `SIE_BASE_URL`, `SIE_EMBED_MODEL`, `SIE_RERANK_MODEL`, `SIE_EXTRACT_MODEL`,
`SIE_LLM_MODEL` (default `zai-org/GLM-5.3-Flash:relay`), `SIE_DOC_MODEL` (default `docling`),
`SIE_OCR_MODEL` (default `docling:ocr`), `SIE_VLM_MODEL` (default `lightonai/LightOnOCR-3-4B:markdown`, 2nd OCR try),
optional `SIE_PROVISION_TIMEOUT` (s, default 60), `SIE_VLM_TIMEOUT` (300), `SIE_LLM_TIMEOUT` (180), `SIE_DOC_MAX_TOKENS` (16384).

Routing (live-verified 2026-11-20, D-008):
- **LLM** → `chat_completions` on GLM-5.3-Flash relay (~1s warm, supports `json_schema`). It is a reasoning model and the relay
  rejects `reasoning_effort` / `enable_thinking` / `thinking`, so `max_tokens` is floored at 512 and `<think>` blocks are stripped.
- **Documents** (PDF/DOCX/CSV) → `extract(docling, Item(document=bytes))` → text (~0.6s) → `llm()` with `json_schema`.
- **Scans** (png/jpg) → `extract(docling:ocr, Item(images=[bytes]))` (~6s) → if empty/failed, LightOnOCR via `extract` (cold) → `llm()`.
  (LightOnOCR via `generate()` returns "Generation route is unavailable".)

| Function | Returns |
|---|---|
| `available() -> bool` | |
| `embed(texts: list[str], is_query=None) -> dict` | `{"vectors": list[list[float]] (L2-normalized), "model", "dim", "source"}` — fallback: 256-d hashed trigrams |
| `rerank(query: str, docs: list[str]) -> dict` | `{"results": [{"index", "score", "rank"}] (best first), "model", "source"}` — fallback: token overlap |
| `extract_entities(text: str, labels: list[str]) -> dict` | `{"entities": [{"label", "text", "score"}], "model", "source"}` — fallback: regex vin/dtc/bay/vehicle/promise_time |
| `llm(messages, response_format=None, max_tokens=1024) -> dict` | `{"text", "json" (when response_format), "model", "finish_reason", "source"}` or `{"error"}` |
| `document_text(doc: path\|bytes, filename=None) -> dict` | `{"text", "model", "source"}` (images routed to `ocr_image`) |
| `ocr_image(image: path\|bytes, instruction="") -> dict` | `{"text", "model", "source"}` or `{"error"}` |
| `extract_document(doc, output_schema, instruction="", filename=None) -> dict` | `{"data": dict, "model": "<text>+<llm>", "method": "doc"\|"ocr"\|"csv", "text_chars", "source"}` |
| `parse_statement(path) -> dict` | `{"statement_date", "vendor_name", "lines": [{date, invoice_no, sku, desc, qty, amount, core_credit}], "total", "model", "method", "source"}` — the `parse_vendor_statement` shape minus `vendor_id` |
| `warm(provision_timeout_s=600) -> dict` | `{"role:model": "ok 1.2s" \| "error after …"}` |
| `models() -> dict` | resolved model id per role |

CLI: `uv run python -m tools.integrations.sie warm` · `... sie models` · `... sie statement seed/statements/bayshore_2026-11.pdf`

## senso.py — shop rules (Senso REST)

Env: `SENSO_API_KEY`, `SENSO_BASE_URL` (default `https://apiv2.senso.ai/api/v1`). Fallback: keyword search over `seed/senso_docs/*.md`.

| Function | Returns |
|---|---|
| `search(query: str, max_results: int = 5) -> dict` | `{"answer": str, "passages": [{"content_id", "title", "chunk_text", "score"}], "source"}` |
| `search_context(query: str, max_results: int = 5) -> dict` | `{"passages": [...], "source"}` |
| `add_doc(title: str, text: str, wait: bool = True, timeout_s: float = 60) -> dict` | `{"content_id": str, "status": "complete" \| "processing" \| "duplicate", "source"}` (409 → `duplicate`); fallback writes `runs/cache/senso/added/<slug>.md` and returns `content_id="local:<slug>"` |

## persona.py — Know Your Agent: verify the shop owner (D-006)

Env: `PERSONA_API_KEY`, `PERSONA_TEMPLATE_ID` (`itmpl_...`), optional `PERSONA_REFERENCE_ID` (default `shop-001-owner`), `PERSONA_OWNER_NAME`.

| Function | Returns |
|---|---|
| `verify_owner(reason: str, amount: float, ro_id: str \| None = None, wait_s: float = 0) -> dict` | `{"inquiry_id", "status": "approved" \| "declined" \| "pending", "verified_name", "hosted_url", "method": "persona" \| "simulated"}` |
| `create_inquiry(reason: str, amount: float, ro_id=None) -> dict` | same shape, status usually `pending` |
| `get_status(inquiry_id: str) -> dict` | same shape |
| `simulate_approve(inquiry_id: str) -> dict` | marks a simulated inquiry approved (UI "approve" button) |

## airbyte.py — context layer over shop sheets (D-007)

Env: `AIRBYTE_CLIENT_ID`, `AIRBYTE_CLIENT_SECRET`, `AIRBYTE_WORKSPACE_ID`. Fallback: `seed/shop_sheets/*.csv`.

| Function | Returns |
|---|---|
| `search_shop_data(query: str, stream: str \| None = None, limit: int = 20) -> dict` | `{"records": [{"stream", "id", "fields": dict}], "source": "airbyte" \| "csv"}` (`stream` ∈ `bookings`, `price_sheets`) |
| `list_streams() -> list[str]` | |

## shopify.py — PartsDepot Online (Shopify Admin GraphQL)

Env: `SHOPIFY_SHOP`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `SHOPIFY_API_VERSION`. Fallback: mock vendor `POST http://localhost:8101/v/partsdepot/orders` (env `VENDORS_URL` overrides base).

| Function | Returns |
|---|---|
| `get_token() -> str \| None` | |
| `products(first: int = 50) -> dict` | `{"products": [{"id", "title", "variants": [{"id", "sku", "price", "inventory_quantity"}]}], "source"}` |
| `place_order(lines: list[{"variant_id": str, "qty": int}], note: str = "") -> dict` | `{"shopify_order_id", "admin_url", "total": float, "draft_order_id", "source": "live" \| "fallback"}` or `{"error"}` |

## cognee.py — Sal's learned memory

Env: `COGNEE_URL`, `COGNEE_API_KEY`, optional `COGNEE_DATASET` (default `sal_shop_001`). Fallback: `db.client` facts table if present, else `runs/cache/cognee/facts.jsonl` + keyword recall.

| Function | Returns |
|---|---|
| `remember(text: str, tags: list[str] \| None = None) -> dict` | `{"ok": bool, "source"}` |
| `recall(query: str, top_k: int = 5) -> dict` | `{"facts": [{"text", "tags", "score"}], "source"}` |

## statsig_client.py — gate + dynamic config

Env: `STATSIG_SERVER_SECRET`, optional `STATSIG_CONSOLE_API_KEY`; overrides `SAL_GATE_ROUTING=on|off`, `SAL_POLICY_STRATEGY=cheapest|rules_aware`.

| Function | Returns |
|---|---|
| `check_gate(name: str = "sal_vendor_routing_v2", user_id: str = "shop-001") -> bool` | env override wins |
| `get_config(name: str = "sal_policy", user_id: str = "shop-001") -> dict` | e.g. `{"strategy": "rules_aware"}` |
| `variant() -> dict` | `{"gate_routing_v2": bool, "strategy": str, "source"}` — what the sim passes to Sal |
| `log_event(name: str, value=None, metadata: dict \| None = None, user_id="shop-001") -> None` | |
| `ensure_console_objects() -> dict` | creates the gate/config via Console API if missing |
| `shutdown() -> None` | |

## amplitude.py — custom events (brain owns session instrumentation)

Env: `AMPLITUDE_AI_API_KEY`.

| Function | Returns |
|---|---|
| `track(event_type: str, properties: dict \| None = None, user_id: str = "shop-001", session_id: str \| None = None) -> dict` | `{"ok": bool, "source"}` — fallback appends to `runs/cache/amplitude/events.jsonl` |
| `flush() -> None` | |

## nhtsa.py — vPIC + complaints (no key)

Reads `seed/cache/nhtsa/` first, then live, writes `runs/cache/nhtsa/`.

| Function | Returns |
|---|---|
| `decode_vin(vin: str, model_year: int \| None = None) -> dict` | `{"year", "make", "model", "trim", "engine_l", "cylinders", "raw_source_url", "source"}` |
| `complaints(make: str, model: str, year: int, component_keyword: str \| None = None, top: int = 5) -> dict` | `{"total", "matching", "top": [{"odi", "date", "summary", "components"}], "source_url", "source"}` |

## smoke

`uv run python -m tools.integrations.smoke` → table `service | key? | live call ok? | fallback in use` (no secrets).

## Status / what remains (2026-11-20)

- Verified live: **NHTSA** (vPIC decode + complaints). All other keys were empty at build time → fallbacks exercised; live paths coded against the installed SDK source (`sie_sdk` 0.11.1, `cognee` 1.6.10, `statsig-python-core` 0.24.2, `amplitude`) / official docs.
- **Airbyte:** docs document no REST/SDK record-search endpoint; the only headless path is the hosted MCP (`https://mcp.airbyte.com/mcp`, `Client-Id`/`Client-Secret` headers) tool `execute_external_search_query`, which needs agent connectors + search enabled + a backfill in Airbyte Cloud. Its input schema isn't documented, so we discover it via `list_tools`. Until a Sheet source is connected and backfilled, `search_shop_data` serves `seed/shop_sheets/*.csv` (`source="csv"`).
- **Persona:** headless runs can't finish the hosted flow; `verify_owner` returns `pending` + `hosted_url`; the owner UI calls `persona.approve(inquiry_id)` (live `POST /inquiries/{id}/approve` in sandbox, or simulated).
- **SIE model ids:** if `SIE_*_MODEL` is empty we pick by name from `list_models()` and log the choice to stderr once — copy it into `.env`.
