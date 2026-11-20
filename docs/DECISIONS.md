# Decisions

| ID | Date | Decision | Why | Owner |
|---|---|---|---|---|
| D-001 | 2026-11-20 13:00 PT | Repo `sudhersankv/sal` public; lead runs from T3 Code on Opus 5.5 with background delegates per workstream (not experimental agent teams) | User asked to start immediately; same folder-ownership model as SPEC §6 | lead |
| D-002 | 2026-11-20 13:05 PT | **SIE for all non-agent model calls**: embeddings, rerank, entity extract, small-LLM sub-calls (`chat_completions`), OCR via VLM `generate(images=)`, structured doc extract via `extract(output_schema=)` | User direction; SIE SDK 0.11 supports generate/chat/vision/document inputs; strengthens SIE track; replaces Arcee stretch | lead |
| D-003 | 2026-11-20 13:05 PT | FRI statement reconciliation promoted from stretch → **p1** (bill parsing/OCR showcase). New tools `extract_intake`, `parse_vendor_statement`, `reconcile_statement`; new event `statement.parsed` | User asked for bill parsing/OCR | lead |
| D-004 | 2026-11-20 13:05 PT | No `make` on Windows: `Makefile` targets are one-liners over `scripts/tasks.py`; on Windows run `uv run python scripts/tasks.py <target>` | Toolchain reality | lead |
| D-005 | 2026-11-20 13:05 PT | SIE serverless may cold-provision (SDK waits up to 15 min). Warm models at seed time; every SIE call cached to `runs/cache/sie/` keyed by (model, input hash); replay uses cache | Demo safety | tools |
| D-006 | 2026-11-20 13:20 PT | Keep Senso **and** add **Persona** (KYA): `verify_owner` re-verifies the human owner before any over-cap order (TUE $260 alternator beat in demo) | User: maximize sponsor prizes; Persona is an event partner | lead |
| D-007 | 2026-11-20 13:20 PT | Add **Airbyte** as context layer: bookings + vendor price sheets live in a shop Google Sheet/CSV; Airbyte syncs/searches them (`search_shop_data`). 20-min rule → local CSV fallback | Airbyte is an event partner ("context layer for agents") | lead |
