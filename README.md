<p align="center"><img src="docs/brand/sal-mark.png" width="96" alt="Sal"></p>

# Sal: Your Parts Team

**Small repair shops can't afford a parts department. Sal is one.**

Sal is a personal agent for an independent auto repair shop. It buys the exact part for the car on the lift, watches stock against upcoming bookings and restocks before you run out. It scores your vendors, catches missing core credits on their bills, and gets smarter week to week. It works inside the owner's rules, and every decision has a paper trail.

> *PartsTech is the catalog. Sal is the parts guy.*

- **Live dashboard:** https://sal-parts-team.fly.dev
- **Talk to Sal on Telegram:** [@handysalbot](https://t.me/handysalbot)
- **Connect your own agent (MCP):** `https://sal-parts-team.fly.dev/mcp` with a bearer token, see [docs/MCP.md](docs/MCP.md)
- **Deploys:** every push to `main` runs checks and deploys to Fly (`.github/workflows/deploy.yml`)
- **Demo video:** _link_

---

## What it does

| You say / it notices | Sal does | Trail |
|---|---|---|
| *"Civic in bay 2, P0141, VIN 19XFB2F58EE214879, promised by 3 PM"* | Decodes the VIN, finds the **downstream** O2 sensor, compares 3 vendors, rejects ValuMax (no-buy list + 2 comebacks), the upstream sensor (wrong part), NTK (misses 3 PM) and the 2-day shipper. Quotes the car owner $82, orders Denso at Mission for $41, ETA 10:20. | Each rejection cites the shop rule, the comeback ROs and the SIE match verdict |
| An alternator costs $260, over the $200 cap | Refuses to buy on its own. Escalates, **verifies it's really the owner (Persona)**, then orders. | The policy guard sits in the tools, not the prompt |
| Nothing. It's Wednesday. | Reads the next 7 days of bookings against stock and finds 4 items short. Orders 9 filters + 4 wipers on the vendor's **Shopify** store, adding brake cleaner ×6 to clear free shipping. | The reason cites the restock rule (R6) |
| The Bayshore statement arrives (PDF or a phone photo) | **Parses the bill** (docling / OCR on SIE), reconciles it against purchase history, finds **$90 in missing core credits** and drafts a dispute. It doesn't send it. | Line-level diff against the ledger |
| Sunday | Builds vendor scorecards in one SQL query (Bayshore was 37.5% late on starters), proposes a routing rule with evidence, and the owner approves. The rule is written to **Senso** and remembered in **Cognee**, the **Statsig** gate flips, and before/after metrics follow. | Evidence from SingleStore + Cognee |
| *"are we low on anything for the Civics next week?"* … *"yeah go get them"* | Answers in plain language, then does it. | Every message and action is in Activity & Trace |

**Policy lives in tools, not prompts.** The spend cap, no-buy list and vendor-routing gate are enforced in code inside every `place_*` tool. A blocked order returns an escalation, never an order. Sal can propose rules but can never approve them.

## Architecture (30 seconds)

```
 Telegram (@handysalbot) ─┐
 Dashboard approvals ─────┼─▶ Sal (Claude Agent SDK) ──MCP──▶ sal-tools (FastMCP, 26 tools, policy guard)
 Firedrill drills ────────┤                                      │
 Week simulator ──────────┘                                      ├─ Superlinked SIE   extract · embed · rerank · LLM · OCR · docs
                                                                 ├─ Senso             the owner's rules (context layer)
                                                                 ├─ SingleStore       ledger + vector search
                                                                 ├─ Cognee            what Sal has noticed (memory)
                                                                 ├─ Persona           verify the human before over-cap spend
                                                                 ├─ Statsig           routing gate + policy config
                                                                 ├─ Shopify           real restock orders
                                                                 └─ NHTSA             VIN decode + complaints
             every tool emits an audit event ─▶ ui/server (event log + SSE) ─▶ dashboard
             every agent session ─▶ Amplitude Agent Analytics
```

Sal's own reasoning runs on Claude. **Every other model call goes through Superlinked SIE**: entity extraction, embeddings, reranking, small-LLM sub-calls, document parsing and OCR.

## Sponsors: what each one does in Sal

### Senso: the shop's trusted context
The owner's mandate lives in Senso: spend cap, markup matrix, no-buy list, urgent-job rules, restock rules, vendor profiles and preferred brands. `get_shop_rules` calls `POST /org/search`, and every decision event cites the Senso `content_id`s it relied on. When the owner approves a Sunday rule, it is written back with `POST /org/kb/raw`. **Senso holds what the owner decided.**

### Superlinked SIE: small models for every non-agent call
| Job | Model | Call |
|---|---|---|
| Pull VIN / DTC / bay / promise time from the tech's message | `fastino/gliner2-large-v1` | `extract` |
| Embed vendor listings for matching | `Qwen/Qwen3-Embedding-4B` (2560-d) | `encode` |
| "Same part?" verdicts (catches the upstream sensor sold as downstream) | `Qwen/Qwen3-Reranker-4B` | `score` |
| Parse vendor statements (PDF) | `docling` → `zai-org/GLM-5.3-Flash:relay` with a JSON schema | `extract` + `chat_completions` |
| OCR a photographed bill | `docling:ocr` / `lightonai/LightOnOCR-3-4B` | `extract` |

### SingleStore: the ledger and the vectors
All shop state (vendors, catalog, inventory, bookings, repair orders, orders, 90-day purchase history, rules, metrics) plus `vendor_catalog.embedding VECTOR(2560)`.

Hybrid vector match:
```sql
SELECT vendor_id, sku, brand, description, DOT_PRODUCT(embedding, %s :> VECTOR(2560)) AS score
FROM vendor_catalog WHERE oem_part_no = %s OR description LIKE %s ORDER BY score DESC LIMIT 10
```
The vendor scorecard is one query (`SCORECARD_SQL` in `tools/impl.py`): late rate, missed core credits and price index per vendor.

### Firedrill: drills against a synthetic car owner
Sal is registered as a `jsonl-process.v1` local agent (`firedrill/driver.py`). The Monday scenario runs against the persona **Dana Ruiz** (approves quotes ≤ $150, otherwise asks one question), with evaluations for "never orders ValuMax", "never exceeds the spend cap" and "orders before the cutoff". See `firedrill/README.md`.

### Amplitude Agent Analytics + Statsig: ship a behavior change and measure it
Statsig gate `sal_vendor_routing_v2` + dynamic config `sal_policy`. The simulator picks the arm, never the agent. Every Sal run is an Amplitude agent session (`session_id = run_id`), with each message, tool call, cost and latency tracked, plus custom events `sal_order_placed`, `sal_escalation` and `sal_rule_applied` carrying the variant.

### Cognee: what Sal has noticed
Observed facts, such as "Bayshore late on 3 of last 8 starter deliveries" and "ValuMax O2 comeback on RO-0977", are stored with `remember` and recalled when Sal proposes rules. **Senso = what the owner decided; Cognee = what Sal noticed.**

### Persona: Know Your Agent
Before any order over the spend cap, `verify_owner` opens a Persona inquiry so the approval provably comes from the verified owner, not from whoever has the chat open.

### Also: Shopify, NHTSA, Telegram
Wednesday's restock is a real draft → completed order on the vendor's Shopify dev store (Admin GraphQL, client credentials). NHTSA vPIC decodes the VIN and NHTSA complaints give vehicle context only; brand quality comes from the shop's own comeback history. Staff talk to Sal on Telegram.

## Run it

```bash
uv sync --extra memory
cp .env.example .env                 # fill in keys; anything missing uses its documented fallback
uv run python -m seed                # deterministic seed (seed=42) + Senso/Cognee/Shopify/SIE loaders
uv run python scripts/tasks.py dev   # vendors :8101 · dashboard + events :8100 · web :5173
uv run python -m uvicorn sim.api:app --port 8102
uv run python scripts/tasks.py bot   # Telegram
uv run python scripts/tasks.py week  # simulated Mon→Sun
uv run python scripts/tasks.py check # ruff + tests
```
`make <target>` works on macOS/Linux.

## Real vs simulated (honest labels)

- **Real:** NHTSA calls, SIE models, Claude agent, MCP tools, policy enforcement, SQL scorecards and vector match, statement parsing, Telegram, Firedrill drills, plus every sponsor whose key is configured (see the dashboard → Activity → Integrations).
- **Simulated:** the shop (Mission Street Auto), the vendors (Mission Auto Supply, Bayshore Parts Co., PartsDepot Online) and ValuMax are **fictional**. Prices are illustrative. Part numbers are real where verified (`seed/SOURCES.md`); the rest are marked illustrative. No real money moves.

## Team
_names + emails_
