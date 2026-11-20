"""`python -m seed`: run every loader in order. Each loader skips cleanly without its key."""
from __future__ import annotations

import importlib
import sys
import traceback

STEPS = ["seed.sheets", "seed.statements", "seed.load_db", "seed.load_senso", "seed.load_embeddings",
         "seed.load_cognee", "seed.load_shopify"]


def main() -> int:
    rc = 0
    for mod in STEPS:
        print(f"== {mod}", flush=True)
        try:
            m = importlib.import_module(mod)
        except ModuleNotFoundError as e:
            if e.name == mod:
                print(f"SKIP {mod}: not implemented yet")
                continue
            raise
        try:
            m.main() if hasattr(m, "main") else m.write()
        except SystemExit as e:
            rc |= int(e.code or 0)
        except Exception:
            traceback.print_exc()
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
