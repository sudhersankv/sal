# Human-only setup

Put every secret in `./.env` (git-ignored). Never paste keys in chat or commit them.
Priority: **p0** = demo depends on it · **p1** = has a fallback (SPEC §8) but loses sponsor depth.

| # | Item | Where | .env keys | Prio |
|---|---|---|---|---|
| 1 | Anthropic API key (Sal's runtime) | console.anthropic.com → API Keys | `ANTHROPIC_API_KEY` | p0 |
| 2 | Senso API key | Senso org → API Keys page (org admin) | `SENSO_API_KEY` | p0 |
| 3 | SingleStore Helios | portal.singlestore.com → free Starter workspace → create database `sal` → Connect → connection string | `SINGLESTORE_URL` (`user:pass@host:3306/sal`) | p0 (fallback: sqlite) |
| 4 | Shopify dev store + app | dev.shopify.com/dashboard → create dev store "PartsDepot Online" → create app in the **same org**, scopes `write_draft_orders, read_products, write_products, read_orders` → install on the store → client id/secret | `SHOPIFY_SHOP`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET` | p1 (fallback: mock vendor) |
| 5 | Statsig | console.statsig.com → Settings → Keys → Server Secret (+ Console API key so Sal creates gate `sal_vendor_routing_v2` + config `sal_policy`) | `STATSIG_SERVER_SECRET`, `STATSIG_CONSOLE_API_KEY` | p1 |
| 6 | Amplitude | project with **Agent Analytics** enabled → Settings → Projects → API key | `AMPLITUDE_AI_API_KEY` | p1 |
| 7 | Superlinked SIE | Superlinked console (no card) → API key | `SIE_API_KEY` | p1 (fallback: regex + exact join) |
| 8 | Cognee Cloud | Cognee Cloud → tenant URL + API key | `COGNEE_URL`, `COGNEE_API_KEY` | p1 (fallback: facts table) |
| 9 | Firedrill | needs Node ≥ 22.23.4 (or 24.11.1+): `npm i -g firedrill-run && firedrill init` (browser sign-in) → Billing → Event code **TOKENSAND** | `FIREDRILL_WORKSPACE` | p1 (fallback: UI approve button + ledger) |
| 10 | Team names + emails | for the submission form | — (tell the lead) | p0 at submit |

When done, tell the lead "done". The lead runs a smoke check per service and reports a status table.
