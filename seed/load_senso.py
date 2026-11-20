"""Seed the shop's 9 rule docs into Senso (POST /org/kb/raw, poll until complete).

Always writes local copies to seed/senso_docs/*.md and mirrors them into rules_docs.
Stores content ids in seed/senso_ids.json. Idempotent: existing ids are kept; 409 = duplicate.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from db.client import get_db
from db.migrate import migrate
from seed.senso_content import DOCS

HERE = Path(__file__).parent
DOCS_DIR = HERE / "senso_docs"
IDS = HERE / "senso_ids.json"


def write_local() -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    for slug, title, text in DOCS:
        (DOCS_DIR / f"{slug}.md").write_text(f"# {title}\n\n{text}\n", encoding="utf-8")


def main() -> int:
    write_local()
    ids = json.loads(IDS.read_text()) if IDS.exists() else {}
    from tools.integrations import senso

    if not senso.available():
        print("SKIP senso: no key (local docs in seed/senso_docs/)")
    else:
        for slug, title, text in DOCS:
            if ids.get(slug, {}).get("status") == "complete":
                continue
            r = senso.add_doc(title, text, wait=True, timeout_s=120)
            if "error" in r or r.get("source") == "fallback":
                print(f"senso {slug}: {r.get('error') or 'fell back'}")
                continue
            ids[slug] = {"title": title, "content_id": r.get("content_id"), "status": r.get("status")}
            print(f"senso {slug}: {r.get('status')} {r.get('content_id')}")
            IDS.write_text(json.dumps(ids, indent=1))
    db = get_db()
    migrate(db)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for slug, title, text in DOCS:
        db.execute("DELETE FROM rules_docs WHERE doc_id=%s", (slug,))
        db.execute("INSERT INTO rules_docs (doc_id, title, text, senso_content_id, updated_at) VALUES (%s,%s,%s,%s,%s)",
                   (slug, title, text, ids.get(slug, {}).get("content_id"), now))
    print(f"senso: {sum(1 for v in ids.values() if v.get('content_id'))}/{len(DOCS)} docs in Senso")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
