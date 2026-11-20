"""Data access for sal-tools: SingleStore via `db.client` (owned by data/T1), local sqlite fixture fallback.

SQL in this package is written portable (MySQL/SingleStore + sqlite) with `%s` placeholders.
`query()` tries `db.client.query(sql, params)` first; on any error (module missing, DB down,
table empty for a read) it runs the same SQL against an in-memory sqlite built from
tools/fixtures.py, so the server always answers.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from typing import Any

from tools import fixtures as fx

log = logging.getLogger("sal-tools.data")
_lock = threading.RLock()
_local: sqlite3.Connection | None = None

_SQLITE_DDL = """
CREATE TABLE vendors (vendor_id TEXT PRIMARY KEY, name TEXT, kind TEXT, cutoff_local TEXT,
  free_ship_threshold REAL, account_terms TEXT);
CREATE TABLE parts (part_id TEXT PRIMARY KEY, oem_part_no TEXT, part_type TEXT, position TEXT,
  description TEXT, has_core INTEGER, core_charge REAL, source_url TEXT);
CREATE TABLE fitments (part_id TEXT, year INTEGER, make TEXT, model TEXT, engine_l REAL, dtc TEXT, notes TEXT);
CREATE TABLE vendor_catalog (vendor_id TEXT, sku TEXT, vendor_part_no TEXT, oem_part_no TEXT, brand TEXT,
  description TEXT, price REAL, qty_on_hand INTEGER, eta_minutes INTEGER, shopify_variant_id TEXT, embedding TEXT,
  PRIMARY KEY(vendor_id, sku));
CREATE TABLE inventory (sku TEXT PRIMARY KEY, name TEXT, part_type TEXT, qty INTEGER, min_qty INTEGER, max_qty INTEGER);
CREATE TABLE bookings (booking_id TEXT PRIMARY KEY, date TEXT, service_code TEXT, vehicle TEXT, parts_needed TEXT);
CREATE TABLE repair_orders (ro_id TEXT PRIMARY KEY, opened_at TEXT, vin TEXT, dtc TEXT, complaint TEXT, bay INTEGER,
  customer_id TEXT, status TEXT);
CREATE TABLE orders (order_id TEXT PRIMARY KEY, vendor_id TEXT, ro_id TEXT, placed_at TEXT, promised_at TEXT,
  delivered_at TEXT, total REAL, channel TEXT, external_ref TEXT, run_id TEXT);
CREATE TABLE order_lines (order_id TEXT, sku TEXT, brand TEXT, part_type TEXT, qty INTEGER, unit_price REAL,
  core_charge REAL);
CREATE TABLE purchase_history (order_id TEXT, vendor_id TEXT, brand TEXT, part_type TEXT, placed_at TEXT,
  promised_at TEXT, delivered_at TEXT, unit_price REAL, comeback INTEGER, core_credit_due REAL,
  core_credit_received REAL);
CREATE TABLE rules (rule_id TEXT PRIMARY KEY, title TEXT, rule_text TEXT, status TEXT, evidence TEXT,
  senso_content_id TEXT, created_at TEXT);
CREATE TABLE metrics (run_id TEXT, day TEXT, variant TEXT, name TEXT, value REAL);
"""


def _insert(conn, table, rows):
    if not rows:
        return
    cols = list(rows[0].keys())
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
    conn.executemany(sql, [[json.dumps(r[c]) if isinstance(r[c], (list, dict)) else r[c] for c in cols]
                           for r in rows])


def local() -> sqlite3.Connection:
    global _local
    with _lock:
        if _local is None:
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.executescript(_SQLITE_DDL)
            _insert(conn, "vendors", fx.VENDORS)
            _insert(conn, "parts", fx.PARTS)
            _insert(conn, "fitments", fx.FITMENTS)
            _insert(conn, "vendor_catalog", [{**r, "embedding": None} for r in fx.VENDOR_CATALOG])
            _insert(conn, "inventory", fx.INVENTORY)
            _insert(conn, "bookings", fx.BOOKINGS)
            _insert(conn, "purchase_history", fx.PURCHASE_HISTORY)
            conn.commit()
            _local = conn
        return _local


def reset_local() -> None:
    """Tests: rebuild the fixture DB."""
    global _local
    with _lock:
        _local = None


def _db_client():
    if os.environ.get("SAL_TOOLS_DATA", "").lower() == "fixtures":
        return None
    try:
        import contextlib
        import sys

        from db.client import get_db
        with contextlib.redirect_stdout(sys.stderr):  # stdout is the MCP channel
            return get_db()
    except Exception:
        return None


def _rows(res: Any) -> list[dict]:
    if res is None:
        return []
    out = []
    for r in res:
        out.append(dict(r) if not isinstance(r, dict) else r)
    return out


def _local_query(sql: str, params: tuple | list = ()) -> list[dict]:
    with _lock:
        cur = local().execute(sql.replace("%s", "?"), tuple(params))
        return [dict(r) for r in cur.fetchall()]


def query(sql: str, params: tuple | list = (), *, allow_empty_fallback: bool = True) -> tuple[list[dict], str]:
    """Returns (rows, backend): backend is db.client's ('singlestore' | 'sqlite') or 'fixtures'."""
    client = _db_client()
    if client is not None:
        try:
            rows = _rows(client.query(sql, tuple(params)))
            if rows or not allow_empty_fallback:
                return rows, getattr(client, "backend", "db")
        except Exception as e:  # noqa: BLE001
            log.warning("db.client.query failed, using fixtures: %s", e)
    return _local_query(sql, params), "fixtures"


def execute(sql: str, params: tuple | list = ()) -> str:
    """Best-effort write: SingleStore if available, and always the local fixture DB."""
    backend = "fixtures"
    client = _db_client()
    if client is not None:
        try:
            client.execute(sql, tuple(params))
            backend = getattr(client, "backend", "db")
        except Exception as e:  # noqa: BLE001
            log.warning("db.client.execute failed: %s", e)
    try:
        with _lock:
            local().execute(sql.replace("%s", "?"), tuple(params))
            local().commit()
    except Exception as e:  # noqa: BLE001
        log.warning("local execute failed: %s", e)
    return backend


def vector_search(table: str, vector: list[float], k: int = 5, where: str = "", params: tuple = ()) -> list[dict] | None:
    client = _db_client()
    if client is None or not hasattr(client, "vector_search"):
        return None
    try:
        return _rows(client.vector_search(vector, k=k, where=where or None, params=params, table=table))
    except Exception as e:  # noqa: BLE001
        log.warning("vector_search failed: %s", e)
        return None


def parse_json(v: Any) -> Any:
    if isinstance(v, (bytes, str)):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v
