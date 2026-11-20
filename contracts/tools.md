# sal-tools MCP — tool contracts (SPEC §7.2)

Lead-owned. Change only via the lead + docs/DECISIONS.md.

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


## Additions (lead, 2026-11-20, see docs/DECISIONS.md D-002/D-003)

| Tool | Input | Output | Auto-emits | Backing |
|---|---|---|---|---|
| `extract_intake` | `{text}` | `{vin, dtc, bay, vehicle, promise_time, complaint}` | — (feeds `repair_order.created`) | SIE `extract` (gliner2) → fallback regex |
| `parse_vendor_statement` | `{path}` (pdf, csv, png/jpg scan) | `{vendor_id, statement_date, lines:[{date, invoice_no, sku, desc, qty, amount, core_credit}], total, model, method: doc\|ocr\|csv}` | `statement.parsed` | SIE `extract(output_schema=…)` on PDF/CSV; SIE VLM `generate(images=…)` OCR for scans; fallback: csv reader |
| `reconcile_statement` | `{vendor_id, lines[]}` | `{missing_core_credits:[{order_id, sku, due}], total_due, dispute_draft}` | `escalation` (dispute drafted, not sent) | SingleStore join vs `purchase_history` |

**Model routing rule:** Sal's reasoning loop = Claude (Agent SDK, `SAL_MODEL`). Every other model call (extraction, matching, rerank, OCR, document parsing, short text sub-tasks like reason-chip wording) goes through **Superlinked SIE** via `tools/sie.py` (one shared client; caches responses in `runs/cache/sie/` for demo safety). No other model provider in tools.
