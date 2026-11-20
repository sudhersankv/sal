# Sal: working rules

- Read SPEC.md. Contracts in `contracts/` are **lead-only**; need a change → tell the lead with the exact diff.
- Stay in your workstream's folders (SPEC §6). Never edit another stream's files, `pyproject.toml`, or `uv.lock` (ask the lead for deps).
- Model routing: Sal's agent loop is Claude; every other model call goes through Superlinked SIE (`tools/sie.py`). See docs/DECISIONS.md D-002.
- Secrets only in `.env`; read via env. Never print or commit them.
- Run `uv run python scripts/tasks.py check` (= `make check`) before every PR.
- Windows dev box: no `make`; use `scripts/tasks.py`.
