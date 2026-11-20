"""Remember Sal's initial observed facts in Cognee (dataset sal_shop_001). Idempotent via seed/cognee_loaded.json."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from db.client import get_db

MARK = Path(__file__).with_name("cognee_loaded.json")


def main() -> int:
    from tools.integrations import cognee

    if not cognee.available():
        print("SKIP cognee: no key (facts table holds the seed facts)")
        return 0
    done = set(json.loads(MARK.read_text())) if MARK.exists() else set()
    facts = get_db().query("SELECT text, tags FROM facts WHERE source='seed' ORDER BY fact_id")
    n = 0
    for f in facts:
        h = hashlib.sha1(f["text"].encode()).hexdigest()[:12]
        if h in done:
            continue
        r = cognee.remember(f["text"], f["tags"])
        if r.get("ok") and r.get("source") == "live":
            done.add(h)
            n += 1
        else:
            print(f"cognee remember failed/fell back: {r.get('error') or r.get('source')}")
            break
    MARK.write_text(json.dumps(sorted(done)))
    print(f"cognee: remembered {n} new, {len(done)}/{len(facts)} total")
    probe = cognee.recall("Bayshore late starters", top_k=3)
    print(f"cognee recall probe: source={probe.get('source')} n={len(probe.get('facts', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
