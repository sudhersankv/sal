# SPEC — Sal: Your Parts Team

> **One line:** Small repair shops can't afford a parts department. Sal is one — a proactive agent that tracks stock, buys parts, restocks and manages vendors for one independent shop, inside the owner's rules, with every decision traced to a source.

| | |
|---|---|
| Event | tokens& Personal Agents Hackathon, SF, Fri Nov 20 2026 |
| Theme | "Build a shopping agent with an audit trail" — reliable context, a meaningful action, show the info + steps behind it |
| **Hard deadline** | **Submission 4:30 PM PT.** Finalist demos 5:00 PM. 3-minute demo. |
| Submission needs | Public/accessible GitHub repo · demo video link · description + tools used · team names + emails |
| Owner | Sudhersan KV |
| Status | LOCKED scope. Changes only via the lead, recorded in `docs/DECISIONS.md`. |

---

## 0. Read this first (rules for every agent)

1. **Contracts are law.** `contracts/` (event schema, tool signatures, DB DDL, policy) is owned by the lead. Never change a contract in your own branch. Ask the lead.
2. **Stay in your folder.** Each workstream owns specific directories (§6). Touching another workstream's files = merge conflict = lost time.
3. **Tracer bullet first.** Get the thinnest end-to-end Monday flow working with mocks before adding depth. Depth is worthless if Monday doesn't run.
4. **Demo > completeness.** Anything not visible in the 3-minute demo or not required by a sponsor track is out of scope.
5. **Never block on a sponsor.** Every sponsor integration has a documented fallback (§8). If an API fights you for >20 min, switch to the fallback, log it in `docs/DECISIONS.md`, and tell the lead.
6. **Secrets** live only in `.env` (git-ignored). Never commit keys. Never print keys in logs or events.
7. **Real data, honestly labeled.** Real part brands/numbers/fitments where verified; anything mocked is labeled mocked in UI and README.
8. **No fake real businesses.** Vendor storefronts/counters are **fictional companies**. Real part *brands* (Bosch, Denso…) appear only as catalog data, never as a fake vendor.

---

## 1. Product

### 1.1 Problem
Independent repair shops (2–6 bays) buy dozens of cheap parts a week. Nobody owns the parts job, so money leaks:
- **Wrong or poor-quality parts** → comebacks; the shop pays the labor twice.
- **Stock-outs** on consumables (oil filters, wipers, bulbs, fluids) → cars wait, bays stay blocked.
- **Vendor drift** — late deliveries and missed core-charge credits that nobody tracks.
- Big dealers have a parts department. Small shops have the owner at 9 PM, or nobody.

### 1.2 Sal
Sal is the shop's **parts team as one agent**. Roles:

| Role | Sal does |
|---|---|
| Buyer | Sources the exact part per repair; picks vendor by urgency, quality, price |
| Inventory clerk | Tracks stock; reads upcoming bookings; restocks before stock-outs |
| Vendor manager | Builds scorecards from purchase history; proposes routing rules |
| Accounts (stretch) | Reconciles vendor statements; catches missing core credits |

Sal operates on a **mandate** the owner sets once (stored in Senso): margin target, no-buy list, spend cap, preferred vendors, markup matrix.

**Policy lives in tools, not prompts.** Spend cap and no-buy list are enforced in code inside the order tools. A blocked order returns an `escalation`, never an order.

### 1.3 Positioning vs existing tools
Multi-vendor search exists (e.g. PartsTech). **Sal is not a catalog. Sal is the parts person who uses catalogs** — proactive, owns outcomes (stock, vendor performance), and every decision has a paper trail. Pitch line: *"PartsTech is the catalog. Sal is the parts guy."*

---

## 2. Judging map

Judging criteria (from the event): **Autonomy · Idea · Technical implementation · Tool use (sponsor tools) · Presentation (3-min demo).**

| Criterion | How Sal wins it |
|---|---|
| Autonomy | Whole week runs without manual steps; only the car owner's approval and the owner's rule approval are human gates (by design, shown as policy) |
| Idea | Real, specific, recurring pain; "parts department for shops too small to have one" |
| Technical | MCP tool server, policy-in-tools, event-sourced audit trail, real-data seeding, A/B gated behavior change |
| Tool use | 6 sponsors, each with a real job (§8) |
| Presentation | 3D line-art shop + live audit trail + goal meters; one story: Mon buy → Wed restock → Sun gets smarter |

Sponsor prize tracks targeted (priority order): **Senso · Firedrill · Amplitude+Statsig · SingleStore · Superlinked SIE · Cognee.** Optional: Arcee (route cheap calls), Guild (not planned).

---

## 3. Scope

### In scope (must ship)
- **MON — urgent buy:** repair order → identify exact part → vet → compare vendors → choose → quote with markup → car owner approval → order placed (+ payment record) → delivered.
- **WED — proactive restock:** no trigger. Sal reads next 7 days of bookings + inventory → shortfalls → bundled restock order **placed as a real order on a Shopify dev store**.
- **SUN — gets smarter:** vendor scorecard from history → proposes a routing rule with evidence → owner approves → rule written to Senso + remembered in Cognee → Statsig gate turns on → before/after metrics.
- **Audit trail** for every step (decision, reason, sources).
- **Dashboard:** 3D line-art shop + timeline + part cards + goal meters + "Next day ▶".
- **Demo safety:** replay mode from a recorded event log.

### Stretch (only after must-ship is green)
1. FRI — vendor statement reconciliation → missing core credits → dispute drafted (not sent).
2. Staff chat with Sal (Telegram bot) over the same tools.
3. Price-match negotiation on Monday (deterministic vendor policy).
4. Arcee model routing for cheap sub-calls.

### Non-goals
Real B2B portal logins · live web scraping · browser automation · real payments · auth/multi-tenant · mobile · production hardening.

---

## 4. Architecture

```
                      ┌────────────────────────────── contracts/ (lead-owned) ─────────────────────────────┐
                      │ events.schema.json · tools.md · db.sql · policy.md · demo_script.md                │
                      └─────────────────────────────────────────────────────────────────────────────────────┘

 ┌──────────── sim/ (week runner) ────────────┐        ┌──────────── ui/ (dashboard) ───────────────┐
 │ day=mon|wed|sun → trigger payloads          │        │ Vite + three.js + TS                        │
 │ Statsig: picks policy variant per run       │        │ SSE /stream → 3D shop, timeline, meters     │
 │ Firedrill: drives Sal in drills (jsonl)     │        │ replay mode: plays events.jsonl             │
 └───────────────┬─────────────────────────────┘        └───────────────▲─────────────────────────────┘
                 │ invokes                                              │ events (SSE)
 ┌───────────────▼──────────── agent/ (Sal) ────────────────┐   ┌───────┴──────── ui/server (FastAPI) ───┐
 │ Claude Agent SDK (Python), model from SAL_MODEL           │──▶│ POST /events  → append events.jsonl     │
 │ system prompt = persona + mandate summary                 │   │ GET  /stream  (SSE)                      │
 │ MCP servers: sal-tools (stdio)                            │   │ GET  /state   (meters, inventory)        │
 │ Amplitude Agent Analytics: one session per day-run        │   └──────────────────────────────────────────┘
 └───────────────┬───────────────────────────────────────────┘
                 │ MCP (stdio)
 ┌───────────────▼──────────── tools/ (sal-tools MCP, FastMCP) ───────────────────────────────────────────┐
 │ decode_vin · get_complaints · get_shop_rules · search_vendor · match_listings · get_inventory          │
 │ get_bookings · get_vendor_history · place_counter_order · place_shopify_order · request_owner_approval  │
 │ remember_fact · recall_facts · propose_rule · emit_event                                               │
 │ POLICY GUARD (spend cap, no-buy list) inside every place_* tool                                        │
 └──┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬───────────────────────────────────┘
    │          │          │          │          │          │          │
  NHTSA     Senso      SIE       SingleStore  vendors/   Shopify    Cognee        Firedrill synthetic
 (vPIC +   (REST:     (embed,    (ledger +    (FastAPI   (Admin     (remember/   Gmail + Stripe
 complaints) search,   rerank,    vectors)    mock       GraphQL    recall)      (owner approval,
             kb/raw)   extract)               counters)  draft      payment record)
                                                         orders)
```

**Runtime flow (Monday):** `sim run --day mon` posts the tech's message → invokes Sal with the trigger → Sal calls tools; every tool call that matters emits an event → UI animates → order placed → Sal's final summary event.

**Why MCP:** all Sal capabilities are one MCP server, so the same tools serve the agent, Firedrill drills, and (stretch) staff chat. Senso has an official MCP server, but it authenticates via OAuth browser sign-in, which a headless agent run can't do reliably; Sal therefore calls Senso's REST API with an API key inside `sal-tools`. Coding agents MAY use the Senso MCP during development (seeding/inspecting the KB).

---

## 5. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.12 (backend), TypeScript (UI) | `uv` for Python deps |
| Agent | `claude-agent-sdk` (Python) | MCP via `ClaudeAgentOptions(mcp_servers=..., allowed_tools=["mcp__sal-tools__*"])` |
| Sal's model | `SAL_MODEL` env, default `claude-sonnet-5-5` (fast) | switch to `claude-opus-5-5` if quality needs it |
| Tool server | FastMCP (`mcp` / `fastmcp` package), stdio | one server: `tools/server.py` |
| Mock vendors | FastAPI + uvicorn | port 8101 |
| UI server | FastAPI (SSE via `sse-starlette`) | port 8100 |
| UI | Vite + TypeScript + three.js | port 5173 |
| DB | SingleStore Helios (free starter workspace) via `singlestoredb` | |
| Tests | `pytest`, `httpx`, Playwright smoke (optional) | |
| Task runner | `Makefile` | `make dev`, `make seed`, `make demo`, `make check` |

---

## 6. Repo layout & ownership

```
sal/
├── CLAUDE.md                 # lead: agent rules, pointers to SPEC + contracts
├── SPEC.md                   # this file
├── README.md                 # lead + T5 at the end: pitch, run, per-sponsor sections
├── Makefile                  # lead
├── .env.example              # lead
├── contracts/                # LEAD ONLY
│   ├── events.schema.json
│   ├── tools.md
│   ├── db.sql
│   ├── policy.md
│   └── demo_script.md
├── docs/
│   ├── DECISIONS.md          # lead (anyone may append via PR)
│   └── SETUP.md              # human setup steps (generated by wizard)
├── seed/                     # T1 data
├── db/                       # T1 data (connection helper, migrations)
├── vendors/                  # T2 tools
├── tools/                    # T2 tools
├── agent/                    # T3 brain
├── sim/                      # T4 sim
├── firedrill/                # T4 sim (descriptor.json, plan.json, scenarios)
├── ui/                       # T5 dashboard (ui/server + ui/web)
└── tests/contract/           # lead (contract tests every stream must pass)
```

---

## 7. Contracts

### 7.1 Event schema (`contracts/events.schema.json`)

Every visible action emits exactly one event. Producers: Sal (via `emit_event` tool or tool-side auto-emit), sim, tools. Transport: `POST http://localhost:8100/events` (JSON body). UI reads `GET /stream` (SSE, one event per message). All events also append to `runs/<run_id>/events.jsonl`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SalEvent",
  "type": "object",
  "required": ["id", "run_id", "ts", "day", "type", "actor", "summary"],
  "properties": {
    "id":      {"type": "string", "pattern": "^evt_[0-9a-z]+$"},
    "run_id":  {"type": "string"},
    "ts":      {"type": "string", "format": "date-time", "description": "SIMULATED shop time, ISO 8601"},
    "day":     {"enum": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]},
    "type":    {"enum": [
      "repair_order.created", "part.identified", "context.retrieved", "vendors.compared",
      "part.rejected", "part.chosen", "quote.sent", "approval.requested", "approval.received",
      "order.placed", "order.delivered", "payment.recorded", "inventory.checked", "stock.low",
      "restock.planned", "escalation", "scorecard.built", "rule.proposed", "rule.approved",
      "memory.saved", "gate.enabled", "metrics.updated", "sal.summary", "error"
    ]},
    "actor":   {"enum": ["sal", "tech", "owner", "car_owner", "vendor", "system"]},
    "summary": {"type": "string", "maxLength": 140, "description": "One line, human readable, shown in timeline"},
    "reason":  {"type": "string", "maxLength": 280},
    "sources": {"type": "array", "items": {
      "type": "object", "required": ["name"],
      "properties": {
        "name": {"enum": ["Senso", "NHTSA", "SingleStore", "SIE", "Cognee", "Shopify", "Firedrill", "Statsig", "Amplitude", "Vendor", "Shop"]},
        "ref":  {"type": "string", "description": "rule id, content_id, order id, SQL table, URL…"},
        "url":  {"type": "string"}
      }}},
    "money":   {"type": "object", "properties": {
      "wholesale": {"type": "number"}, "retail": {"type": "number"}, "saved": {"type": "number"}, "currency": {"const": "USD"}}},
    "refs":    {"type": "object", "description": "ids to link entities: ro_id, order_id, part_no, vendor_id, sku, rule_id"},
    "data":    {"type": "object", "description": "type-specific payload, see tools.md"}
  }
}
```

**3D mapping (UI must implement):**

| Event type | 3D reaction |
|---|---|
| `repair_order.created` | car (line-art) rolls onto the next free lift; floating tag with RO id |
| `vendors.compared` | 3 vendor cards float in (2D overlay anchored to the counter) |
| `part.rejected` | that card slides away with reason |
| `order.placed` (counter) | van line-art departs vendor gate, arrives at the shop door |
| `order.placed` (shopify) | parcel drops onto the shelf |
| `stock.low` | shelf bin empties / pulses accent |
| `order.delivered` | bin fills; part icon flies to the car on the lift |
| `rule.approved` | wall scoreboard flips to the new rule |
| `escalation` | owner's office light pulses; card shows "needs owner" |

### 7.2 Tool signatures (`contracts/tools.md`) — sal-tools MCP

All tools return JSON. All money in USD floats. All tools that represent a decision-relevant action **auto-emit** the matching event (so Sal can't forget to log). Errors return `{"error": {"code": "...", "message": "..."}}`, never raise into the agent.

| Tool | Input | Output | Auto-emits | Backing |
|---|---|---|---|---|
| `decode_vin` | `{vin}` | `{year, make, model, trim, engine_l, cylinders, raw_source_url}` | `part.identified` (partial) | NHTSA vPIC |
| `get_complaints` | `{make, model, year, component_keyword}` | `{total, matching, top:[{odi, date, summary}], source_url}` | `context.retrieved` | NHTSA complaints |
| `get_shop_rules` | `{question}` | `{answer, passages:[{content_id, title, chunk_text}]}` | `context.retrieved` (sources=Senso content_ids) | Senso `POST /org/search` |
| `identify_part` | `{year, make, model, engine_l, dtc?, symptom?}` | `{oem_part_no, part_type, position, notes, candidates:[...]}` | `part.identified` | SingleStore `fitments` + `parts` |
| `search_vendor` | `{vendor_id, oem_part_no}` | `{listings:[{vendor_id, sku, vendor_part_no, brand, desc, price, qty_on_hand, eta_minutes, core_charge}]}` | — | vendors/ mock or Shopify catalog |
| `match_listings` | `{oem_part_no, listings[]}` | `{results:[{sku, verdict: same\|variant\|different, score}]}` | `vendors.compared` | SIE encode + score; SingleStore vector search |
| `get_brand_history` | `{brand, part_type}` | `{purchases, comebacks, comeback_rate}` | `context.retrieved` | SingleStore `purchase_history` |
| `compute_quote` | `{wholesale}` | `{retail, markup_pct, tier_rule_id}` | — | markup matrix (seeded from Senso doc; deterministic) |
| `request_owner_approval` | `{ro_id, customer_id, line_items[], total}` | `{approval_id, status: approved\|declined\|pending, channel}` | `quote.sent`, `approval.requested`, `approval.received` | Firedrill synthetic Gmail (fallback: UI button) |
| `place_counter_order` | `{vendor_id, sku, qty, ro_id}` | `{order_id, eta, total}` or `{escalation}` | `order.placed` / `escalation` | vendors/ mock |
| `place_shopify_order` | `{lines:[{variant_id, qty}], note}` | `{shopify_order_id, admin_url, total}` or `{escalation}` | `order.placed` / `escalation` | Shopify Admin GraphQL draft order → complete |
| `record_payment` | `{ro_id, customer_id, amount}` | `{payment_id}` | `payment.recorded` | Firedrill synthetic Stripe (fallback: ledger row) |
| `get_inventory` | `{}` | `{items:[{sku, name, qty, min_qty, max_qty}]}` | `inventory.checked` | SingleStore |
| `get_bookings` | `{days}` | `{bookings:[{date, service_code, vehicle, parts_needed[]}]}` | — | SingleStore |
| `plan_restock` | `{}` | `{lines:[{sku, need, have, order_qty}], vendor_suggestion}` | `stock.low` (per item), `restock.planned` | deterministic from bookings+inventory |
| `get_vendor_history` | `{vendor_id?, part_type?, days}` | `{per_vendor:[{vendor_id, orders, late, late_rate, missed_core_credits, avg_price_index}]}` | `scorecard.built` | SingleStore |
| `propose_rule` | `{title, rule_text, evidence[]}` | `{rule_id, status:"pending_owner"}` | `rule.proposed` | ledger |
| `approve_rule` | `{rule_id}` (called by sim/owner UI only; **excluded from Sal** via `disallowed_tools=["mcp__sal-tools__approve_rule"]` — Sal can propose rules, never approve them) | `{senso_content_id, statsig_gate}` | `rule.approved`, `gate.enabled` | Senso kb/raw + Statsig |
| `remember_fact` | `{text, tags[]}` | `{ok}` | `memory.saved` | Cognee `remember` |
| `recall_facts` | `{query}` | `{facts:[...]}` | `context.retrieved` | Cognee `recall` |
| `emit_event` | `SalEvent` (partial ok) | `{id}` | itself | ui/server |

**Policy guard (`tools/policy.py`, applied in every `place_*`):**
1. Reject if brand ∈ no-buy list (from Senso rules cache, refreshed at server start).
2. Reject if order total > `SPEND_CAP` (default $200) unless `approval_id` from the shop **owner** is attached.
3. Reject if Statsig gate `sal_vendor_routing_v2` is ON and part_type ∈ routed types and vendor ≠ routed vendor.
4. On reject → return `{"escalation": {...}}` and emit `escalation`.

### 7.3 Database (`contracts/db.sql`, SingleStore)

```sql
CREATE TABLE vendors (vendor_id VARCHAR(32) PRIMARY KEY, name TEXT, kind ENUM('counter','online'),
  cutoff_local TIME, free_ship_threshold DECIMAL(10,2), account_terms TEXT);
CREATE TABLE parts (part_id VARCHAR(48) PRIMARY KEY, oem_part_no VARCHAR(64), part_type VARCHAR(48),
  position VARCHAR(32), description TEXT, has_core BOOL, core_charge DECIMAL(10,2), source_url TEXT);
CREATE TABLE fitments (part_id VARCHAR(48), year INT, make VARCHAR(32), model VARCHAR(48),
  engine_l DECIMAL(3,1), dtc VARCHAR(8), notes TEXT, KEY(make, model, year));
CREATE TABLE vendor_catalog (vendor_id VARCHAR(32), sku VARCHAR(64), vendor_part_no VARCHAR(64),
  oem_part_no VARCHAR(64), brand VARCHAR(48), description TEXT, price DECIMAL(10,2),
  qty_on_hand INT, eta_minutes INT, shopify_variant_id VARCHAR(64), embedding VECTOR(1024),
  PRIMARY KEY(vendor_id, sku));
CREATE TABLE inventory (sku VARCHAR(64) PRIMARY KEY, name TEXT, part_type VARCHAR(48), qty INT, min_qty INT, max_qty INT);
CREATE TABLE bookings (booking_id VARCHAR(32) PRIMARY KEY, date DATE, service_code VARCHAR(32),
  vehicle TEXT, parts_needed JSON);
CREATE TABLE repair_orders (ro_id VARCHAR(16) PRIMARY KEY, opened_at DATETIME, vin VARCHAR(17),
  dtc VARCHAR(8), complaint TEXT, bay INT, customer_id VARCHAR(32), status VARCHAR(16));
CREATE TABLE orders (order_id VARCHAR(48) PRIMARY KEY, vendor_id VARCHAR(32), ro_id VARCHAR(16), placed_at DATETIME,
  promised_at DATETIME, delivered_at DATETIME, total DECIMAL(10,2), channel VARCHAR(16), external_ref TEXT, run_id VARCHAR(48));
CREATE TABLE order_lines (order_id VARCHAR(48), sku VARCHAR(64), brand VARCHAR(48), part_type VARCHAR(48),
  qty INT, unit_price DECIMAL(10,2), core_charge DECIMAL(10,2));
CREATE TABLE purchase_history (order_id VARCHAR(48), vendor_id VARCHAR(32), brand VARCHAR(48), part_type VARCHAR(48),
  placed_at DATETIME, promised_at DATETIME, delivered_at DATETIME, unit_price DECIMAL(10,2),
  comeback BOOL, core_credit_due DECIMAL(10,2), core_credit_received DECIMAL(10,2));
CREATE TABLE rules (rule_id VARCHAR(32) PRIMARY KEY, title TEXT, rule_text TEXT, status VARCHAR(16),
  evidence JSON, senso_content_id VARCHAR(64), created_at DATETIME);
CREATE TABLE metrics (run_id VARCHAR(48), day VARCHAR(3), variant VARCHAR(32), name VARCHAR(48), value DOUBLE);
```
Vector dim = the SIE embedding model's dimension. **T1 confirms the dim on first encode call and updates the DDL via the lead before seeding.** Vector insert: pass the vector as a JSON array string; similarity via `DOT_PRODUCT` on normalized vectors (= cosine).

### 7.4 Policy doc (`contracts/policy.md`) — also seeded into Senso as the shop's rules
- R1 Spend cap: any single order > $200 needs owner approval.
- R2 Markup matrix (wholesale → retail): ≤$25 ×2.5 · $25–75 ×2.0 · $75–200 ×1.7 · >$200 ×1.5.
- R3 Margin target: weekly parts margin ≥ 45%.
- R4 No-buy list: brand **"ValuMax"** (fictional economy brand) for sensors, after comebacks.
- R5 Urgent jobs (car on a lift): local counter only; promise time must beat the bay's promise time.
- R6 Restocks: online channel preferred; bundle to clear free-shipping threshold when within $25.
- R7 Preferred brands for O2 sensors: Denso, NTK, Bosch.
- R8 Never pay with a customer's card on file without explicit approval.

### 7.5 Environment (`.env.example`)
```
# Sal runtime
ANTHROPIC_API_KEY=
SAL_MODEL=claude-sonnet-5-5
SPEND_CAP=200
DEMO_MODE=live            # live | replay
# Senso
SENSO_API_KEY=
SENSO_BASE_URL=https://apiv2.senso.ai/api/v1
# Superlinked SIE Serverless
SIE_API_KEY=
SIE_BASE_URL=https://api.superlinked.com
SIE_EMBED_MODEL=          # T1 fills from SIE catalog (Qwen3-Embedding-4B family)
SIE_RERANK_MODEL=         # Qwen3-Reranker-4B family
SIE_EXTRACT_MODEL=        # gliner2 family
# SingleStore
SINGLESTORE_URL=          # user:pass@host:3306/sal
# Cognee Cloud
COGNEE_URL=               # https://<tenant>.aws.cognee.ai
COGNEE_API_KEY=
# Amplitude Agent Analytics
AMPLITUDE_AI_API_KEY=
# Statsig
STATSIG_SERVER_SECRET=
STATSIG_CONSOLE_API_KEY=  # optional: lets agents create the gate/config via API
# Shopify (Dev Dashboard app, client credentials grant)
SHOPIFY_SHOP=             # yourstore.myshopify.com
SHOPIFY_CLIENT_ID=
SHOPIFY_CLIENT_SECRET=
SHOPIFY_API_VERSION=2026-10
# Firedrill (CLI signs in via browser; event code TOKENSAND)
FIREDRILL_WORKSPACE=
# Stretch
TELEGRAM_BOT_TOKEN=
ARCEE_API_KEY=
```

---

## 8. Sponsor integrations (what, how, acceptance, fallback)

### 8.1 Senso — the shop's trusted context  *(track: Best Use of Senso)*
- **Job:** the mandate, rules R1–R8, markup matrix, vendor profiles and preferred brands live in Senso. Sal queries it for every decision and cites `content_id`s in events. Approved Sunday rules are written back.
- **API facts:** base `https://apiv2.senso.ai/api/v1`, header `X-API-Key`. Add doc: `POST /org/kb/raw {"title","text"}` → 202 with `kb_node_id`; poll `GET /org/kb/nodes/{kb_node_id}` until `content.processing_status == "complete"`. Search with answer: `POST /org/search {"query"}` → `answer`, `results[{content_id,title,chunk_text,score,rank}]`. Passages only: `POST /org/search/context`. Identical text → 409; credits exhausted → 402.
- **Docs to seed (T1):** `Shop mandate`, `Markup matrix`, `No-buy list`, `Urgent job rules`, `Restock rules`, `Vendor profile — Mission Auto Supply`, `Vendor profile — Bayshore Parts Co.`, `Vendor profile — PartsDepot Online`, `Preferred brands by part type`.
- **Acceptance:** `get_shop_rules("rules for O2 sensors")` returns an answer citing the no-buy list and preferred-brands docs with `content_id`s; Monday events show those ids.
- **Fallback:** local markdown copies in `seed/senso_docs/` + keyword search; events still cite doc titles. Pitch loses Senso depth — avoid.

### 8.2 Firedrill — synthetic world for car owner + payment, and drills  *(track: Best Use of Firedrill)*
- **Job:** (a) the car owner persona receives the quote via synthetic **Gmail** and replies approve/decline; (b) synthetic **Stripe** (test mode, no money moves) records the parts payment; (c) a **drill campaign** runs the Monday scenario N times and reports pass rate on evaluations ("never orders ValuMax", "never exceeds spend cap", "order placed before cutoff").
- **Facts:** CLI `npm install --global firedrill-run` (Node 22.23.4+/24.11.1+/26.13.1+; not 23/25) → `firedrill init` (browser sign-in, workspace) → `firedrill plan` → `firedrill apply <plan-id> --approve --follow` → `firedrill runner enroll` → `firedrill run --plan plan.json --descriptor descriptor.json --campaign <id>` → `firedrill report <id>`. Driver for Sal: `jsonl-process.v1` (print `READY` on stdout, JSON-only stdout after, logs to stderr) or `http.v1`. Firedrill provides an MCP server + skill for coding agents — **T4 must install it and follow Firedrill's own coding-agent setup page** rather than guess formats. Event credits: code **TOKENSAND** (500 credits) applied under Billing → Event code.
- **Acceptance:** one campaign report with ≥5 Monday drills and visible evaluation results; screenshot in README.
- **Fallback (live demo):** `request_owner_approval` uses an in-UI "Car owner (simulated)" approve button; `record_payment` writes a ledger row. Drills still shown from a pre-run report.

### 8.3 Amplitude Agent Analytics + Statsig — ship a change, measure it  *(track: Best Use of Amplitude or Statsig)*
- **Statsig job:** gate `sal_vendor_routing_v2` (the Sunday rule) and dynamic config `sal_policy` (`strategy`: `cheapest` | `rules_aware`). The **sim** reads them before each run and passes the variant to Sal/tools — the agent never chooses its own arm.
- **Statsig facts:** `pip install statsig-python-core`; `Statsig(secret, StatsigOptions()).initialize().wait()`; `check_gate(StatsigUser("shop-001"), "sal_vendor_routing_v2")`; `get_dynamic_config(...)`; `log_event(user, event_name, value, metadata)`; `shutdown().wait()` at exit.
- **Amplitude job:** every Sal day-run = one agent session (`session_id = run_id`, `user_id = "shop-001"`, agent name `sal`). Track each user/trigger message, each assistant message, each tool call, cost/latency. Custom events: `sal_order_placed`, `sal_escalation`, `sal_rule_applied` with variant property.
- **Amplitude facts:** `pip install amplitude-ai`; `AmplitudeAI(api_key=...)`; `ai.agent("sal")`; `agent.session(user_id=..., session_id=...)`; `with session.run() as s: s.track_user_message(...)`; call `ai.flush()` in a `finally`. Sal runs through the Claude Agent SDK (not a raw client), so instrument **manually** from the SDK message stream (tool_use blocks, assistant text, ResultMessage usage). If the Python manual-tracking API differs from expectation, fall back to Amplitude's HTTP API with `[Agent]`-prefixed event properties.
- **Acceptance:** run week with gate OFF, then ON → dashboard shows before/after (on-time %, avg cost, escalations); Amplitude chart screenshot of sessions split by variant.
- **Fallback:** metrics computed from our own `metrics` table and shown in the dashboard; Statsig values from `.env` overrides.

### 8.4 SingleStore — the ledger and the vectors  *(track: Best Use of SingleStoreDB)*
- **Job:** all shop state (§7.3) + `vendor_catalog.embedding` for part matching. Reconciliation/scorecards are SQL.
- **Facts:** `pip install singlestoredb`; `import singlestoredb as s2; conn = s2.connect(os.environ["SINGLESTORE_URL"])`. `VECTOR(n)` column; insert the vector as a JSON array string; `DOT_PRODUCT` with normalized vectors = cosine; filter with normal SQL `WHERE`.
- **Acceptance:** `match_listings` uses a SQL vector query (`ORDER BY DOT_PRODUCT(embedding, :q) DESC LIMIT k` with `WHERE oem_part_no ...` hybrid filter) and the scorecard is one SQL query; both visible in README with the query text.
- **Fallback:** SQLite + numpy cosine behind the same `db/` interface (switch by `DB_BACKEND=sqlite`).

### 8.5 Superlinked SIE — small models for matching and extraction  *(tracks: SIE harness / technical build)*
- **Job:** (a) embed catalog listings + OEM descriptions for matching; (b) rerank candidates for "same part?"; (c) extract VIN/DTC/bay/vehicle from the tech's free-text message (GLiNER2).
- **Facts:** `pip install sie-sdk`; `from sie_sdk import SIEClient; from sie_sdk.types import Item`; `SIEClient(base_url=..., api_key=...)`; `client.encode(model, Item(text=...))` → `result["dense"]`; `client.score(model, query_item, items)` → `result["scores"][{rank, score}]` (cross-encoder logits: only order matters); `client.extract(model, Item(text=...), labels=[...])` → `result["entities"][{label,text}]`. Serverless endpoints are `/v1/encode/{model}`, `/v1/score/{model}`, `/v1/extract/{model}`; base URL `https://api.superlinked.com`. Cookbook model names: Qwen3-Embedding-4B, Qwen3-Reranker-4B, gliner2-large-v1 — **T1/T2 confirm exact ids in the SIE model catalog and put them in `.env`**.
- **Acceptance:** Monday "same/variant/different" verdicts come from SIE scores; intake extraction pulls VIN + P0141 + bay from the tech's sentence.
- **Fallback:** regex extraction for VIN/DTC; matching by exact `oem_part_no` join.

### 8.6 Cognee — Sal's learned memory  *(track: Best Use of Cognee)*
- **Job:** facts Sal *observed* (not rules the owner set): "Bayshore late on 3 of last 8 starter deliveries", "ValuMax O2 sensor comeback on RO-0977". Sunday proposal cites recalled facts. Clean split: **Senso = what the owner decided; Cognee = what Sal noticed.**
- **Facts:** `pip install cognee`; `await cognee.serve(url=COGNEE_URL, api_key=COGNEE_API_KEY)`; `await cognee.remember(text, dataset_name="sal_shop_001")`; `await cognee.recall(query_text=...)`; `await cognee.disconnect()`.
- **Acceptance:** Sunday `rule.proposed` event has ≥2 sources from Cognee and ≥1 from SingleStore.
- **Fallback:** `facts` table in SingleStore with keyword recall.

### 8.7 Shopify — where the restock purchase really happens (no prize; credibility)
- **Job:** "PartsDepot Online" (fictional) is a **Shopify dev store**. Wednesday restock = real order in its admin.
- **Facts:** since Jan 1 2026, new legacy custom apps can't be created in the store admin; create the app in the **Dev Dashboard**, install it on a dev store **in the same organization**, then exchange credentials: `POST https://{shop}/admin/oauth/access_token` with `grant_type=client_credentials`, `client_id`, `client_secret`. Scopes: `write_draft_orders`, `read_products`, `write_products`, `read_orders`, `read_payment_terms` (if exposed). Flow: `draftOrderCreate(lineItems:[{variantId, quantity}], note)` → `draftOrderComplete(id, paymentPending: true)` or with payment terms (net-30 = realistic commercial terms). Order appears in the merchant's orders list.
- **Risk:** a developer reported losing dev-store access after using draft orders on a development store. Use a throwaway store.
- **Acceptance:** Wednesday `order.placed` has `external_ref` = Shopify order GID and an `admin_url`; demo cuts to the Shopify admin.
- **Fallback:** online channel served by `vendors/` mock (`kind=online`), labeled.

### 8.8 NHTSA — real public vehicle data (no key)
- VIN decode: `GET https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvalues/{VIN}?format=json&modelyear={YEAR}`.
- Complaints: `GET https://api.nhtsa.gov/complaints/complaintsByVehicle?make=&model=&modelYear=`.
- **Honesty note:** NHTSA complaints are about the **vehicle's components**, not aftermarket brands. Use them as "known failure patterns on this car" context. **Brand quality comes from the shop's own comeback history** (SingleStore) and the no-buy rule (Senso). Never claim NHTSA complaints about a parts brand.
- Cache responses in `seed/cache/nhtsa/` so the demo works offline.

---

## 9. Seed data (T1)

**Principles:** real brands, real OEM/aftermarket part numbers and fitments **only where verified from a public source** (record URL in `parts.source_url` and `seed/SOURCES.md`); prices snapshotted from public listings today; anything unverified is marked `illustrative=true` and shown as such.

- **Vehicles (fitments):** 2014 Honda Civic 1.8L (demo hero), 2016 Ford F-150 3.5L, 2018 Toyota Camry 2.5L, 2015 Nissan Altima 2.5L, 2017 Chevrolet Silverado 5.3L, 2019 Honda CR-V 1.5T.
- **Parts (~40):** O2 sensors (upstream/downstream), brake pads/rotors, alternators, starters, calipers (with core charges), serpentine belts, ignition coils, wiper blades, oil filters, cabin/engine air filters, bulbs, brake cleaner, ATF/coolant.
- **Brands:** Denso, NTK, Bosch, ACDelco, Motorcraft, Moog, Gates, Wagner, Akebono, plus fictional **ValuMax** (economy, the no-buy brand).
- **Vendors (fictional):** `mission` Mission Auto Supply (counter, ETA 45–70 min, pricier, reliable) · `bayshore` Bayshore Parts Co. (counter, cheapest, late on starters/alternators, misses core credits) · `partsdepot` PartsDepot Online (Shopify, cheapest, 2-day ship, free shipping ≥ $150).
- **Vendor part numbers differ per vendor** (prefix schemes) so matching is real work.
- **Inventory:** consumables with min/max; oil filters for common fitments deliberately low before Wednesday.
- **Bookings:** next 7 days from Wednesday: 12 oil changes (mixed fitments), 3 brake jobs, 2 wiper replacements.
- **Purchase history:** 90 days, ~150 orders, generated by a seeded RNG (`seed=42`) with planted patterns: Bayshore late on 3/8 starter+alternator deliveries; Bayshore missed 2 core credits; ValuMax O2 sensor comeback ×2; Mission on-time 95%.
- **Demo hero VIN:** a VIN that NHTSA decodes as a **2014 Honda Civic** (verify by calling vPIC; store the response in cache). Do not invent a VIN without verifying the decode.
- **Shopify products:** create ~15 products/variants on the dev store for the consumables (titles, SKUs, prices); store variant GIDs in `vendor_catalog.shopify_variant_id`.

Scripts: `seed/generate.py` (deterministic), `seed/load_singlestore.py`, `seed/load_senso.py`, `seed/load_shopify.py`, `seed/load_cognee.py` (initial observed facts), `make seed` runs all, idempotent.

---

## 10. Demo scenario — exact expected behavior (`contracts/demo_script.md`)

Simulated week of **Mon Nov 16 – Sun Nov 22, 2026**. Shop: "Mission Street Auto" (fictional), 4 bays.

### MON 09:12 — urgent buy (target: ~14 events)
1. `repair_order.created` (actor tech): "Civic in bay 2, P0141, VIN …, customer promised by 3 PM" → SIE extract → RO-1042.
2. `part.identified`: decode VIN (NHTSA) → 2014 Civic 1.8L; P0141 → **downstream** O2 sensor (bank 1 sensor 2), OEM part no from `fitments`.
3. `context.retrieved` ×3: Senso rules (R4, R5, R7), NHTSA complaints for the car (context only), SingleStore brand history (ValuMax 2 comebacks), Cognee facts.
4. `vendors.compared`: Mission, Bayshore, PartsDepot listings; SIE verdicts (one Bayshore listing is the *upstream* sensor → `different`).
5. `part.rejected`: ValuMax @ Bayshore $33 — R4 no-buy + 2 comebacks (sources Senso, SingleStore).
6. `part.rejected`: Denso @ PartsDepot $38 — 2-day ship violates R5.
7. `part.rejected` (or not offered): Bayshore NTK — ETA 3:10 PM > promise.
8. `part.chosen`: Denso @ Mission $41, ETA 10:20.
9. `quote.sent` / `approval.requested`: $41 → $82 (R2 ×2.0) + labor line (fixed, from RO) to car owner via Firedrill Gmail.
10. `approval.received` (actor car_owner): approved.
11. `order.placed`: Mission order, `money.wholesale=41`.
12. `payment.recorded`: Firedrill Stripe test payment for the approved total.
13. `order.delivered` (sim advances clock) → `sal.summary`: one paragraph + meters update.

### WED 07:30 — proactive restock (no trigger)
1. `inventory.checked` → `get_bookings(7)` → `plan_restock`.
2. `stock.low` ×3 (oil filters for Civic/CR-V/Camry, wipers).
3. `restock.planned`: 9 filters + 4 wipers; total $132 → adds brake cleaner ×6 to clear $150 free shipping (R6) → `reason` cites R6.
4. `order.placed` on **Shopify** (real order GID, admin URL) → `sal.summary`.

### SUN 18:00 — gets smarter
1. `scorecard.built`: SQL over 90 days → Bayshore late 37.5% on starters/alternators, 2 missed core credits ($90).
2. `context.retrieved`: Cognee recall of observed facts.
3. `rule.proposed`: "Route starters & alternators to Mission Auto Supply" with evidence (SingleStore + Cognee sources) and projected savings.
4. Owner approves (UI button / sim) → `rule.approved` (written to Senso, remembered in Cognee) → `gate.enabled` (`sal_vendor_routing_v2` ON).
5. Sim replays a starter job with gate OFF vs ON → `metrics.updated`: on-time %, expected late-penalty cost, escalations. Amplitude shows both variants.

### Stretch FRI 16:00 — statement reconciliation
Bayshore statement (PDF/CSV) → line items → join `purchase_history` → 2 missing core credits → `escalation` "dispute drafted" (not sent).

### Expected escalation demo (optional 10s)
TUE: F-150 alternator $260 → R1 spend cap → `escalation` → owner approves in UI → order placed.

---

## 11. Dashboard spec (T5)

### 11.1 Design direction
Synthesis of three references:
- **Trunk (base)** — "monochrome control room with one signal light". Canvas `#000000`; surfaces `#08090b` → `#232323`; hairlines 1px; text `#dddddd`, muted `#b3b3b5`, tertiary `#89898d`. **One accent `#22c550`, used only for Sal's actions.** No shadows, no gradients; depth = surface steps + hairlines.
- **3D shop drawn like Trunk's hero:** grayscale **line-art** — three.js `EdgesGeometry` + `LineSegments` on primitive geometry (boxes/cylinders). Lifts, cars, shelf with bins, counter, roll-up door, van, office, wall scoreboard. The only colored, moving thing is Sal's accent.
- **B-Line (typography + grid):** mono labels top-left on tiles (part no, fitment), huge thin numerals for meters (`$135`, `47%`), tight grid of light-gray studio tiles (`#e9e9e7` on dark) for parts — each part rendered as the same line-art in its tile (no scraped photos).
- **Shop app (decision moment):** vendor candidate cards float in; rejected cards slide away with reason chips.

**Type:** one grotesk (Inter / Inter Tight): 300 for display & numerals, 400 body, 500 labels. Mono (JetBrains Mono or IBM Plex Mono) for part numbers, prices, timestamps. Scale 11/12/14/15/18/24/36/56. **Radius:** 24 cards, 999 pills, 3 small. **Spacing:** 4px base (4, 8, 12, 20, 24, 32, 48). Max width none (full-bleed app).

### 11.2 Layout (1920×1080 primary, must work at 1440×900)
```
┌ top bar: SAL · Mission Street Auto · simulated clock · day pills MON TUE WED THU FRI SAT SUN · [Next day ▶] · LIVE/REPLAY ┐
├────────────── 3D SHOP (hero, ~58% width) ──────────────┬──────── SAL'S TRAIL (timeline) ────────┤
│ line-art scene, slow orbit, event-driven animations    │ event cards newest-first, expandable:   │
│ floating vendor cards during vendors.compared          │ summary · reason · source chips · money │
├────────────── PARTS / DECISION STRIP ──────────────────┤                                         │
│ part tiles (B-Line grid) or vendor comparison table    │                                         │
├────────────── GOAL METERS ─────────────────────────────┴─────────────────────────────────────────┤
│ margin 47% · saved $ · on-time % · orders · escalations · variant badge (Statsig)                 │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```
- Source chips: Senso / NHTSA / SingleStore / SIE / Cognee / Shopify / Firedrill / Statsig / Amplitude — hairline pills with small sponsor wordmark text (no logos needed).
- Clicking an `order.placed` (Shopify) card opens the admin URL.
- `Next day ▶` calls `POST /sim/next` (ui/server proxies to sim).
- Replay mode: `?replay=runs/demo/events.jsonl&speed=1.5`.

### 11.3 Acceptance
- Runs on `make ui`; replaying `ui/fixtures/sample_week.jsonl` (hand-written by T5 on day one from the schema) animates every event type in §7.1's 3D table.
- 60 fps on a MacBook; no console errors; fonts load offline (bundle them).

---

## 12. Workstreams, tickets, acceptance

Lead creates these as GitHub issues (labels: `ws:data`, `ws:tools`, `ws:brain`, `ws:sim`, `ws:ui`, `ws:lead`, `prio:p0|p1|p2`, `ready-for-agent`), with "blocked by #n" links. **p0 = must for the 3-min demo.**

### Lead (Fable 5.2) — `ws:lead`
- L1 p0 Repo scaffold, Makefile, `.env.example`, `CLAUDE.md`, contracts/ (all of §7), contract tests in `tests/contract/` (schema validation of fixtures; tool I/O shape tests against stubs).
- L2 p0 Human setup intake + `docs/SETUP.md` (wizard).
- L3 p0 Integration: merge cadence, run `make check`, run the full week, fix glue.
- L4 p0 Demo script rehearsal, record video at ~3:45 PM, README + sponsor sections, submission.
- L5 p1 Code review passes (time-boxed).

### T1 data (Opus) — owns `seed/`, `db/`
- D1 p0 `db/` client (SingleStore + sqlite fallback, same interface), apply `contracts/db.sql`.
- D2 p0 Research + write ~40 real parts with sources; hero VIN verified via NHTSA; `seed/SOURCES.md`.
- D3 p0 Deterministic generator: vendors, catalogs (per-vendor numbering), inventory, bookings, 90-day history with planted patterns.
- D4 p0 Senso loader (9 docs, poll until complete, store `content_id`s in `seed/senso_ids.json`).
- D5 p1 SIE embeddings for catalog → `vendor_catalog.embedding`; confirm model ids + dim.
- D6 p1 Shopify loader (products/variants on dev store, store variant GIDs) + token exchange helper `db/shopify_auth.py`.
- D7 p1 Cognee initial facts loader.
- **Done when:** `make seed` is idempotent and green; `python -m db.check` prints row counts; Senso search for "O2 sensor rules" cites R4/R7.

### T2 tools (Opus) — owns `vendors/`, `tools/`
- X1 p0 `vendors/` FastAPI mock: `GET /v/{vendor_id}/search?oem=`, `POST /v/{vendor_id}/orders`, `GET /v/{vendor_id}/orders` (list page for demo), deterministic stock/ETA from seed tables.
- X2 p0 `tools/server.py` FastMCP with every tool in §7.2 (stubs first returning fixture data — **ship stubs in the first 20 min so T3 can start**).
- X3 p0 `tools/policy.py` guard + unit tests (no-buy, spend cap, routing gate).
- X4 p0 Event emission helper (validates against schema before POST; never crashes the tool if UI is down — buffer to jsonl).
- X5 p0 Real backends: NHTSA (+cache), Senso search, SingleStore queries, `compute_quote`, `plan_restock`, scorecard SQL.
- X6 p1 `match_listings` with SIE score + SingleStore vector query.
- X7 p1 `place_shopify_order` (draft → complete) with fallback to mock online vendor.
- X8 p1 `remember_fact` / `recall_facts` (Cognee) with fallback.
- **Done when:** `pytest tests/tools` green; MCP inspector lists all tools; each p0 tool returns schema-valid output on the hero scenario.

### T3 brain (Opus) — owns `agent/`
- B1 p0 `agent/sal.py`: Claude Agent SDK runner `run_day(day, trigger, variant) -> RunResult`; MCP config for sal-tools; `allowed_tools=["mcp__sal-tools__*"]`; `SAL_MODEL`.
- B2 p0 System prompt `agent/prompts/sal.md`: persona (Sal, the shop's parts guy — dry, precise, terse), mandate summary, **procedure per day type**, citation rule ("every decision must cite a tool result source"), escalation rule ("never work around a policy refusal").
- B3 p0 Amplitude instrumentation from the SDK stream (+ HTTP fallback); `ai.flush()` in `finally`.
- B4 p1 Statsig variant passed in from sim → injected into prompt context + tools env.
- B5 p1 Robustness: max turns, tool error handling, deterministic temperature where available; final `sal.summary` always emitted.
- B6 p2 Telegram staff chat (stretch).
- **Done when:** `python -m agent.sal --day mon` produces the §10 Monday event sequence (order may vary ±, all required types present) against stub tools, then against real tools.

### T4 sim (Opus) — owns `sim/`, `firedrill/`
- S1 p0 `sim/run.py --day mon|wed|sun [--variant on|off] [--run-id]`: simulated clock, trigger payloads, owner/car-owner actors (auto-approve with delay, or wait for UI button when `--interactive`), calls `agent.sal.run_day`.
- S2 p0 `POST /sim/next` integration with ui/server (lead wires the proxy).
- S3 p0 Statsig: gate + dynamic config read; `approve_rule` path enables gate (Console API if key provided, else instruct human + read).
- S4 p1 Firedrill: install CLI + Firedrill MCP/skill; descriptor (`jsonl-process.v1` wrapper `firedrill/driver.py` that prints READY and speaks JSONL), synthetic Gmail (car owner persona "Dana Ruiz", approves quotes ≤ $150, asks one question otherwise) + Stripe; scenario "Monday urgent O2 sensor" with evaluations; run ≥5 drills; save report.
- S5 p1 Metrics computation per run/variant → `metrics` table + `metrics.updated` event.
- S6 p1 Replay recorder: `make record` runs mon→wed→sun and saves `runs/demo/events.jsonl` (the demo safety net).
- **Done when:** `make week` runs Mon→Wed→Sun unattended in < 4 min; `make record` produces a replayable log; Firedrill report exists.

### T5 ui (Opus) — owns `ui/`
- U1 p0 `ui/server` FastAPI: `POST /events` (schema-validate, append jsonl, fan out), `GET /stream` SSE, `GET /state` (meters from DB), `POST /sim/next` proxy, replay endpoint.
- U2 p0 `ui/fixtures/sample_week.jsonl` hand-written from the schema (first 15 min) — build everything against it.
- U3 p0 Layout + design tokens + timeline cards with source chips + meters.
- U4 p0 three.js line-art shop scene + event→animation map (§7.1).
- U5 p1 Parts grid tiles (B-Line style) + vendor comparison overlay (Shop-style float/slide).
- U6 p1 Polish: motion timing, number tickers, replay speed control, 1440×900 check.
- **Done when:** replay of fixture and of a real recorded run both play cleanly; screenshot-worthy at 1920×1080.

### Dependency graph (p0 path)
```
L1 contracts ──┬─> X2 tool stubs ──> B1/B2 agent on stubs ──> S1 sim mon ──> L3 integration ──> S6 record ──> L4 demo
               ├─> D1/D2/D3 seed ──> X5 real tools ───────────┘
               └─> U2 fixtures ──> U3/U4 UI ───────────────────────────────────┘
```

---

## 13. Timeline (start ≈ 12:50 PM; submit 4:30 PM)

| Time | Milestone | Gate (lead checks) |
|---|---|---|
| 12:50–1:10 | **M0** intake done, repo + contracts + issues, team spawned | contracts merged; every teammate has ≥3 issues |
| 1:10–1:40 | **M1** stubs everywhere | tools stubs + UI on fixtures + agent runs Monday on stubs |
| 1:40–2:40 | **M2 Tracer bullet** | `make week` Monday live end-to-end with real Senso + SingleStore; event visible in UI |
| 2:40–3:30 | **M3 Depth** | Wed Shopify order real; Sun rule + Statsig + Cognee; Firedrill drills; Amplitude data |
| 3:30–3:45 | **M4 Freeze** | feature freeze; `make record`; bug fixes only |
| 3:45–4:10 | **M5 Demo** | record 3-min video (replay mode fallback), README sponsor sections, screenshots |
| 4:10–4:30 | **M6 Submit** | repo public/accessible, video link, description, names + emails |

If M2 slips past 3:00 PM: cut Firedrill drills to report-from-one-run, cut Cognee to fallback, cut 3D animations to 3 core ones. Never cut: Monday flow, audit trail, Wednesday Shopify order (fallback to mock), Sunday proposal.

---

## 14. Testing strategy
- **Contract tests (lead, run on every merge):** fixtures validate against `events.schema.json`; each tool's stub/real output matches `tools.md` shapes.
- **Policy unit tests (T2):** no-buy, spend cap, routing gate — table-driven.
- **Golden-path test:** `tests/e2e/test_monday.py` runs Monday against stubs and asserts required event types + no `error` events.
- **Smoke:** `make check` = ruff + pytest (fast) + `python -m db.check` + schema validation of the latest run log.
- No exhaustive coverage. Tests exist to keep 5 agents from breaking each other.

## 15. Demo safety
- `DEMO_MODE=replay` plays `runs/demo/events.jsonl` with real timing; the UI looks identical.
- NHTSA and SIE responses cached; Senso answers cached per query in `runs/cache/` after first live run.
- Pre-recorded video is the submission artifact anyway; live demo uses live mode with replay as an instant fallback (one keypress).

## 16. Submission checklist & README
- README sections: pitch · 30-second architecture · how to run (`make setup seed dev week`) · **one section per sponsor: what it does in Sal, the exact calls, a screenshot** · what's real vs mocked · team.
- Demo video ≤ 3 min following §10 and the script in `contracts/demo_script.md`.
- Description text + tools list (copy from README).
- Team names + emails (ask the user).

## 17. Risks
| Risk | Mitigation |
|---|---|
| Agent teams experimental (resume doesn't restore teammates; task status can lag) | Lead keeps GitHub issues as source of truth; nudge stuck teammates; never `/resume` mid-run |
| Merge conflicts between teammates | strict folder ownership; contracts lead-only; each teammate on its own branch/worktree |
| Sponsor API surprises | 20-minute rule → fallback (§8) |
| Shopify dev store/app setup friction | human does it during intake; fallback to mock online vendor |
| Amplitude Agent Analytics is Early Access | HTTP API fallback; dashboard metrics regardless |
| LLM nondeterminism in demo | strict procedures in prompt, deterministic tools, replay mode |
| Time | milestones with cut lists (§13) |

## 18. Human-only setup (collected by the lead at intake)
1. GitHub repo created + `gh auth status` OK (or let lead create it).
2. `ANTHROPIC_API_KEY` for Sal's runtime.
3. **Senso:** org admin creates API key (API Keys page) → `SENSO_API_KEY`.
4. **Superlinked SIE:** sign up (no card), console → API key → `SIE_API_KEY`.
5. **SingleStore Helios:** free workspace + database `sal` → connection string → `SINGLESTORE_URL`.
6. **Cognee Cloud:** tenant URL + API key → `COGNEE_URL`, `COGNEE_API_KEY`.
7. **Amplitude:** project with Agent Analytics enabled → `AMPLITUDE_AI_API_KEY`.
8. **Statsig:** server secret → `STATSIG_SERVER_SECRET`; optionally console API key, else create gate `sal_vendor_routing_v2` and dynamic config `sal_policy` by hand.
9. **Firedrill:** `npm i -g firedrill-run && firedrill init` (browser sign-in), apply event code **TOKENSAND** in Billing.
10. **Shopify:** Dev Dashboard → create dev store "PartsDepot Online" + app (same org) with scopes above → install on store → `SHOPIFY_SHOP`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`.
11. Team names + emails for submission.

## 19. Glossary
- **RO** repair order · **DTC** diagnostic trouble code (P0141 = O2 sensor heater circuit, bank 1 sensor 2 / downstream) · **Core charge** deposit refunded when the old part is returned · **Counter** local commercial parts store delivering by van · **Comeback** car returns because a repair failed · **Mandate** the owner's standing rules for Sal · **Variant** Statsig arm for a run.
