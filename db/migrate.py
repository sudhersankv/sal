"""Apply contracts/db.sql + db/extra.sql to the active backend (idempotent).

    python -m db.migrate            # create missing tables
    python -m db.migrate --reset    # drop + recreate all (destroys data)
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from db.client import DB, get_db, split_sql

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SQL = ROOT / "contracts" / "db.sql"
EXTRA_SQL = ROOT / "db" / "extra.sql"


def statements() -> list[str]:
    out = []
    for p in (CONTRACT_SQL, EXTRA_SQL):
        out += split_sql(p.read_text(encoding="utf-8"))
    return out


def table_name(stmt: str) -> str:
    m = re.search(r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)", stmt, re.I)
    return m.group(1) if m else ""


def to_sqlite(stmt: str) -> str:
    s = re.sub(r"VECTOR\(\d+\)", "TEXT", stmt, flags=re.I)
    s = re.sub(r"ENUM\([^)]*\)", "TEXT", s, flags=re.I)
    s = re.sub(r"\bJSON\b", "TEXT", s)
    s = re.sub(r"DECIMAL\(\d+,\s*\d+\)", "REAL", s, flags=re.I)
    s = re.sub(r",\s*KEY\s*\([^)]*\)", "", s, flags=re.I)
    return s


def contract_vector_dim() -> int:
    m = re.search(r"VECTOR\((\d+)\)", CONTRACT_SQL.read_text(encoding="utf-8"))
    return int(m.group(1)) if m else 0


def migrate(db: DB | None = None, reset: bool = False) -> list[str]:
    db = db or get_db()
    created = []
    existing = set(db.tables())
    for stmt in statements():
        name = table_name(stmt)
        if not name:
            continue
        if reset and name in existing:
            db.execute(f"DROP TABLE {name}")
            existing.discard(name)
        if name in existing:
            continue
        sql = to_sqlite(stmt) if db.backend == "sqlite" else stmt
        db.execute(sql)
        created.append(name)
    return created


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    db = get_db()
    created = migrate(db, reset=a.reset)
    print(f"backend={db.backend} created={created or 'none (all present)'}")


if __name__ == "__main__":
    main()
