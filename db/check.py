"""`python -m db.check`: backend in use + row count per table. Exit 0 even if empty."""
from __future__ import annotations

from db.client import get_db
from db.migrate import migrate


def main() -> int:
    db = get_db()
    migrate(db)
    print(f"backend: {db.backend}" + (f" ({db.path})" if db.backend == "sqlite" else ""))
    for t in db.tables():
        n = db.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]
        print(f"  {t:<18} {n:>6}")
    try:
        emb = db.query("SELECT COUNT(*) AS n FROM vendor_catalog WHERE embedding IS NOT NULL")[0]["n"]
        print(f"  vendor_catalog.embedding non-null: {emb}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
