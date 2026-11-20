"""Fast seed tests on a throwaway sqlite DB."""
from __future__ import annotations

import datetime as dt

import pytest

from db.client import SqliteDB
from seed import expected as X
from seed.generate import build
from seed.load_db import load


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    d = SqliteDB(tmp_path_factory.mktemp("db") / "t.db")
    load(d)
    load(d)  # idempotent
    yield d
    d.close()


def test_deterministic():
    assert build() == build()


def test_counts(db):
    assert db.query("SELECT COUNT(*) n FROM purchase_history")[0]["n"] == X.TOTAL_ORDERS
    assert db.query("SELECT COUNT(*) n FROM orders")[0]["n"] == X.TOTAL_ORDERS
    assert db.query("SELECT COUNT(*) n FROM vendors")[0]["n"] == 3
    assert 38 <= db.query("SELECT COUNT(*) n FROM parts")[0]["n"] <= 45
    assert {r["make"] + " " + r["model"] for r in db.query("SELECT DISTINCT make, model FROM fitments")} >= {
        "Honda Civic", "Ford F-150", "Toyota Camry", "Nissan Altima", "Chevrolet Silverado 1500", "Honda CR-V"}


def test_hero_fitment(db):
    r = db.query("SELECT p.position, p.oem_part_no FROM fitments f JOIN parts p ON p.part_id=f.part_id "
                 "WHERE f.year=2014 AND f.make='Honda' AND f.model='Civic' AND f.dtc=%s", (X.HERO_DTC,))
    assert r == [{"position": "downstream", "oem_part_no": "36532-R1B-A01"}]


def test_hero_listings(db):
    rows = db.query("SELECT vendor_id, brand, price, eta_minutes, description FROM vendor_catalog "
                    "WHERE oem_part_no='36532-R1B-A01'")
    get = {(r["vendor_id"], r["brand"]): r for r in rows}
    assert get[("mission", "Denso")]["price"] == 41.0 and get[("mission", "Denso")]["eta_minutes"] == 68
    assert get[("bayshore", "ValuMax")]["price"] == 33.0
    assert get[("partsdepot", "Denso")]["price"] == 38.0
    assert get[("bayshore", "NTK")]["eta_minutes"] == 358
    assert "UPSTREAM" in get[("bayshore", "Denso")]["description"]


def test_planted_history(db):
    r = db.query("SELECT COUNT(*) n, SUM(CASE WHEN delivered_at > promised_at THEN 1 ELSE 0 END) late "
                 "FROM purchase_history WHERE vendor_id='bayshore' AND part_type IN ('starter','alternator')")[0]
    assert (r["n"], r["late"]) == (8, 3)
    r = db.query("SELECT COUNT(*) n, SUM(core_credit_due - core_credit_received) amt FROM purchase_history "
                 "WHERE core_credit_received < core_credit_due")[0]
    assert (r["n"], r["amt"]) == (2, 90.0)
    r = db.query("SELECT SUM(comeback) c FROM purchase_history WHERE brand='ValuMax' AND part_type='o2_sensor'")[0]
    assert r["c"] == 2
    r = db.query("SELECT COUNT(*) n, SUM(CASE WHEN delivered_at <= promised_at THEN 1 ELSE 0 END) ok "
                 "FROM purchase_history WHERE vendor_id='mission'")[0]
    assert r["ok"] / r["n"] == 0.95


def test_restock_math(db):
    inv = {r["sku"]: r for r in db.query("SELECT * FROM inventory")}
    start = dt.date(2026, 11, 18)
    end = start + dt.timedelta(days=X.BOOKING_WINDOW_DAYS)
    bookings = db.query("SELECT * FROM bookings WHERE date >= %s AND date < %s", (start.isoformat(), end.isoformat()))
    codes = [b["service_code"] for b in bookings]
    assert (codes.count("OIL_CHANGE"), codes.count("BRAKE_FRONT"), codes.count("WIPERS")) == (12, 3, 2)
    need = {}
    for b in bookings:
        for p in b["parts_needed"]:
            need[p["sku"]] = need.get(p["sku"], 0) + p["qty"]
    order = {s: max(0, n + inv[s]["min_qty"] - inv[s]["qty"]) for s, n in need.items()}
    order = {s: q for s, q in order.items() if q}
    price = {r["sku"]: r["price"] for r in db.query("SELECT sku, price FROM vendor_catalog WHERE vendor_id='partsdepot'")}
    types = {s: inv[s]["part_type"] for s in order}
    assert sum(q for s, q in order.items() if types[s] == "oil_filter") == 9
    assert sum(q for s, q in order.items() if types[s] == "wiper_blade") == 4
    total = round(sum(price[s] * q for s, q in order.items()), 2)
    assert total == X.EXPECTED_RESTOCK_TOTAL
    clean = next(s for s in inv if inv[s]["part_type"] == "brake_cleaner")
    assert total + 6 * price[clean] >= X.FREE_SHIP_THRESHOLD > total + 5 * price[clean] - 25


def test_tue_alternator(db):
    r = db.query("SELECT vendor_id, price FROM vendor_catalog WHERE oem_part_no='FL3Z-10346-D' AND brand='Motorcraft' "
                 "AND vendor_id='mission'")
    assert r[0]["price"] == 260.0
    assert not db.query("SELECT 1 FROM vendor_catalog WHERE oem_part_no='FL3Z-10346-D' AND vendor_id='bayshore'")


def test_vector_search_sqlite(db):
    import json
    db.execute("UPDATE vendor_catalog SET embedding=%s WHERE vendor_id='mission' AND brand='Denso' "
               "AND oem_part_no='36532-R1B-A01'", (json.dumps([1.0, 0.0, 0.0]),))
    hits = db.vector_search([1, 0, 0], k=3, where="oem_part_no = %s", params=("36532-R1B-A01",))
    assert hits and hits[0]["brand"] == "Denso" and abs(hits[0]["score"] - 1) < 1e-6
