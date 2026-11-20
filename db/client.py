"""One DB interface for Sal: SingleStore (prod) or sqlite+numpy (fallback).

Usage (any workstream):
    from db.client import get_db
    db = get_db()
    rows = db.query("SELECT * FROM inventory WHERE qty < %s", (5,))
    db.execute("UPDATE inventory SET qty=%s WHERE sku=%s", (10, "PD-BOS-3323"))
    hits = db.vector_search(qvec, k=5, where="oem_part_no = %s", params=("36532-R1A-A01",))

Placeholders: always write `%s` (positional) or `%(name)s` (named). The sqlite
backend translates them. Rows come back as plain dicts with JSON-friendly values
(Decimal -> float, datetime -> 'YYYY-MM-DD HH:MM:SS', TIME -> 'HH:MM:SS').

Backend choice: DB_BACKEND=sqlite, or SINGLESTORE_URL empty -> sqlite file
runs/sal.db (override with SAL_SQLITE_PATH). Otherwise SingleStore.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import json
import os
import re
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VEC_COLS = ("vendor_id, sku, vendor_part_no, oem_part_no, brand, description, price, "
            "qty_on_hand, eta_minutes")
JSON_COLUMNS = {"parts_needed", "evidence", "tags", "fields", "lines"}

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover
    pass


def backend_name() -> str:
    if os.environ.get("DB_BACKEND", "").lower() == "sqlite":
        return "sqlite"
    return "singlestore" if os.environ.get("SINGLESTORE_URL", "").strip() else "sqlite"


def sqlite_path() -> Path:
    return Path(os.environ.get("SAL_SQLITE_PATH") or ROOT / "runs" / "sal.db")


def _norm_value(k: str, v: Any) -> Any:
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, _dt.datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, _dt.timedelta):
        s = int(v.total_seconds())
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
    if isinstance(v, _dt.time):
        return v.strftime("%H:%M:%S")
    if isinstance(v, (bytes, bytearray)) and k == "embedding":
        return None
    if k in JSON_COLUMNS and isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _norm_row(row: dict) -> dict:
    return {k: _norm_value(k, v) for k, v in row.items()}


def _to_vec(v: Any) -> np.ndarray | None:
    if v is None:
        return None
    if isinstance(v, str):
        v = json.loads(v)
    elif isinstance(v, (bytes, bytearray)):
        return np.frombuffer(bytes(v), dtype=np.float32)
    a = np.asarray(v, dtype=np.float32)
    return a


def _normalize(a: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(a))
    return a / n if n else a


def vec_to_json(vec: Sequence[float]) -> str:
    """Serialize a vector for insert into vendor_catalog.embedding (both backends)."""
    return json.dumps([round(float(x), 6) for x in vec])


_NAMED = re.compile(r"%\((\w+)\)s")


def _sqlite_sql(sql: str) -> str:
    sql = _NAMED.sub(r":\1", sql)
    return sql.replace("%s", "?")


class DB:
    """Common interface. Do not instantiate directly; use get_db()."""

    backend: str = "?"

    def query(self, sql: str, params: Sequence | dict | None = None) -> list[dict]:
        raise NotImplementedError

    def execute(self, sql: str, params: Sequence | dict | None = None) -> int:
        raise NotImplementedError

    def executemany(self, sql: str, seq: Iterable[Sequence | dict]) -> int:
        raise NotImplementedError

    def script(self, sql: str) -> None:
        """Run several ';'-separated statements (no params)."""
        for stmt in split_sql(sql):
            self.execute(stmt)

    def tables(self) -> list[str]:
        raise NotImplementedError

    def vector_search(
        self,
        qvec: Sequence[float],
        k: int = 5,
        where: str | None = None,
        params: Sequence | None = None,
        table: str = "vendor_catalog",
        columns: str | None = None,
    ) -> list[dict]:
        """Top-k rows by cosine (DOT_PRODUCT on normalized vectors). Each row gets `score`."""
        raise NotImplementedError

    def close(self) -> None:
        pass


class SqliteDB(DB):
    backend = "sqlite"

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else sqlite_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")

    def query(self, sql, params=None):
        with self._lock:
            cur = self.conn.execute(_sqlite_sql(sql), params or ())
            return [_norm_row(dict(r)) for r in cur.fetchall()]

    def execute(self, sql, params=None):
        with self._lock:
            return self.conn.execute(_sqlite_sql(sql), params or ()).rowcount

    def executemany(self, sql, seq):
        with self._lock:
            self.conn.execute("BEGIN")
            try:
                n = self.conn.executemany(_sqlite_sql(sql), list(seq)).rowcount
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
            return n

    def tables(self):
        rows = self.query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [r["name"] for r in rows]

    def vector_search(self, qvec, k=5, where=None, params=None, table="vendor_catalog", columns=None):
        cols = columns or VEC_COLS
        sql = f"SELECT {cols}, embedding FROM {table} WHERE embedding IS NOT NULL"
        if where:
            sql += f" AND ({where})"
        rows = self.query(sql, params)
        q = _normalize(np.asarray(qvec, dtype=np.float32))
        scored = []
        for r in rows:
            e = r.pop("embedding")
            v = _to_vec(e)
            if v is None or v.shape != q.shape:
                continue
            r["score"] = float(np.dot(_normalize(v), q))
            scored.append(r)
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:k]

    def close(self):
        self.conn.close()


class SingleStoreDB(DB):
    backend = "singlestore"

    def __init__(self, url: str | None = None):
        import singlestoredb as s2

        self.url = url or os.environ["SINGLESTORE_URL"]
        self._s2 = s2
        self._lock = threading.RLock()
        self.conn = s2.connect(self.url, autocommit=True)

    def _cur(self):
        try:
            self.conn.ping(reconnect=True)
        except Exception:
            self.conn = self._s2.connect(self.url, autocommit=True)
        return self.conn.cursor()

    def query(self, sql, params=None):
        with self._lock:
            cur = self._cur()
            cur.execute(sql, params or None)
            if not cur.description:
                return []
            names = [d[0] for d in cur.description]
            return [_norm_row(dict(zip(names, r))) for r in cur.fetchall()]

    def execute(self, sql, params=None):
        with self._lock:
            cur = self._cur()
            cur.execute(sql, params or None)
            return cur.rowcount

    def executemany(self, sql, seq):
        seq = list(seq)
        if not seq:
            return 0
        with self._lock:
            cur = self._cur()
            cur.executemany(sql, seq)
            return cur.rowcount

    def tables(self):
        return sorted(next(iter(r.values())) for r in self.query("SHOW TABLES"))

    def vector_dim(self) -> int | None:
        rows = self.query(
            "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME='vendor_catalog' AND COLUMN_NAME='embedding'"
        )
        m = re.search(r"(\d+)", str(rows[0]["COLUMN_TYPE"])) if rows else None
        return int(m.group(1)) if m else None

    def vector_search(self, qvec, k=5, where=None, params=None, table="vendor_catalog", columns=None):
        cols = columns or VEC_COLS
        q = _normalize(np.asarray(qvec, dtype=np.float32))
        dim = len(q)
        sql = (
            f"SELECT {cols}, DOT_PRODUCT(embedding, %s :> VECTOR({dim})) AS score FROM {table} "
            "WHERE embedding IS NOT NULL"
        )
        if where:
            sql += f" AND ({where})"
        sql += f" ORDER BY score DESC LIMIT {int(k)}"
        return self.query(sql, [vec_to_json(q), *(params or ())])

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


def split_sql(sql: str) -> list[str]:
    sql = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in sql.split(";") if s.strip()]


_DB: DB | None = None
_DB_LOCK = threading.Lock()


def get_db(fresh: bool = False) -> DB:
    """Process-wide DB handle. Falls back to sqlite if SingleStore can't connect."""
    global _DB
    with _DB_LOCK:
        if _DB is not None and not fresh:
            return _DB
        if backend_name() == "singlestore":
            try:
                _DB = SingleStoreDB()
                return _DB
            except Exception as e:  # never block the demo on the DB
                print(f"SKIP singlestore: connect failed ({type(e).__name__}); using sqlite fallback", file=sys.stderr)
        _DB = SqliteDB()
        return _DB


# Convenience module-level API
def query(sql: str, params=None) -> list[dict]:
    return get_db().query(sql, params)


def execute(sql: str, params=None) -> int:
    return get_db().execute(sql, params)


def executemany(sql: str, seq) -> int:
    return get_db().executemany(sql, seq)


def vector_search(qvec, k=5, where=None, params=None, **kw) -> list[dict]:
    return get_db().vector_search(qvec, k=k, where=where, params=params, **kw)


# ---- facts (Cognee fallback; used by tools/integrations/cognee.py) ----
def add_fact(text: str, tags: list[str] | None = None, source: str = "sal") -> str:
    import hashlib

    db = get_db()
    fid = "F-" + hashlib.sha1(text.encode()).hexdigest()[:10]
    db.execute("DELETE FROM facts WHERE fact_id=%s", (fid,))
    db.execute("INSERT INTO facts (fact_id, text, tags, source, created_at) VALUES (%s, %s, %s, %s, %s)",
               (fid, text, json.dumps(tags or []), source, _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return fid


def search_facts(query: str, top_k: int = 5) -> list[dict]:
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    rows = get_db().query("SELECT text, tags FROM facts")
    scored = []
    for r in rows:
        hay = (r["text"] + " " + " ".join(r["tags"] or [])).lower()
        s = sum(1 for w in words if w in hay)
        if s:
            scored.append({"text": r["text"], "tags": r["tags"], "score": float(s)})
    scored.sort(key=lambda r: -r["score"])
    return scored[:top_k]
