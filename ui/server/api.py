"""Owner-app read API (D-010): inventory, orders, jobs, vendors, activity, trace, integrations.

Backed by db.client (sqlite now, SingleStore when SINGLESTORE_URL is set) plus every events.jsonl
under runs/ (and the replay log in DEMO_MODE=replay). Every endpoint degrades to events-only if the
DB is unavailable, so the page never errors.
"""
from __future__ import annotations

import ast
import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs"
FIXTURE = ROOT / "ui/fixtures/sample_week.jsonl"
DEMO_LOG = RUNS / "demo/events.jsonl"

router = APIRouter(prefix="/api")
_cache: dict[str, Any] = {"key": None, "events": []}
_seed_state = {"status": "unknown", "detail": ""}
_live: list[dict] = []  # events POSTed to this server (shared by app.py)


# ------------------------------------------------------------------ helpers
def _q(sql: str, params=None) -> list[dict]:
    try:
        from db import client
        return client.query(sql, params)
    except Exception:  # noqa: BLE001 — no DB / no table: the page falls back to events
        return []


def _num(v, d=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _json(v) -> Any:
    if v is None or isinstance(v, (list, dict)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return None


def markup(w: float) -> float:  # policy R2
    return round(w * (2.5 if w <= 25 else 2.0 if w <= 75 else 1.7 if w <= 200 else 1.5), 2)


def _logs() -> list[Path]:
    logs = sorted(RUNS.glob("*/events.jsonl"))
    if os.environ.get("DEMO_MODE", "").lower() == "replay":
        logs.append(DEMO_LOG if DEMO_LOG.exists() and DEMO_LOG.stat().st_size else FIXTURE)
    return [p for p in dict.fromkeys(logs) if p.exists()]


def all_events() -> list[dict]:
    """Every event we know about, deduped by id, oldest first. Cached on log mtimes."""
    logs = _logs()
    key = tuple((str(p), p.stat().st_mtime, p.stat().st_size) for p in logs) + (len(_live),)
    if _cache["key"] == key:
        return _cache["events"]
    seen, out = set(), []
    for p in logs:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(e, dict) and e.get("id") not in seen:
                seen.add(e.get("id"))
                out.append(e)
    for e in _live:
        if e.get("id") not in seen:
            seen.add(e.get("id"))
            out.append(e)
    out.sort(key=lambda e: str(e.get("ts", "")))
    _cache.update(key=key, events=out)
    return out


def now() -> datetime:
    """Shop 'today' = simulated clock (tools.context) or the latest event."""
    evs = all_events()
    if evs:
        try:
            return datetime.fromisoformat(evs[-1]["ts"]).replace(tzinfo=None)
        except (KeyError, ValueError):
            pass
    try:
        from tools import context
        return context.now().replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return datetime(2026, 11, 18, 9, 0)


def _dt(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "")).replace(tzinfo=None)
    except ValueError:
        return None


# ------------------------------------------------------------------ seed on empty DB (Fly)
def ensure_seeded(background: bool = True) -> None:
    def run():
        try:
            if _q("SELECT COUNT(*) AS n FROM inventory") and _num(_q("SELECT COUNT(*) AS n FROM inventory")[0]["n"]) > 0:
                _seed_state.update(status="ok", detail="db already seeded")
                return
            _seed_state.update(status="seeding", detail="")
            from seed.load_db import load
            res = load()
            _seed_state.update(status="ok", detail=f"seeded {res}")
        except Exception as e:  # noqa: BLE001
            _seed_state.update(status="error", detail=f"{type(e).__name__}: {e}"[:200])
    if background:
        threading.Thread(target=run, daemon=True).start()
    else:
        run()


# ------------------------------------------------------------------ inventory
@router.get("/inventory")
def inventory():
    items = _q("SELECT sku, name, part_type, qty, min_qty, max_qty FROM inventory ORDER BY part_type, name")
    today = now()
    horizon = today + timedelta(days=7)
    need: dict[str, int] = {}
    for b in _q("SELECT booking_id, date, service_code, vehicle, parts_needed FROM bookings"):
        d = _dt(b.get("date"))
        if d and today.date() <= d.date() <= horizon.date():
            for p in _json(b.get("parts_needed")) or []:
                if isinstance(p, dict) and p.get("sku"):
                    need[p["sku"]] = need.get(p["sku"], 0) + int(_num(p.get("qty"), 1))
    incoming: dict[str, dict] = {}
    for r in _q("SELECT ol.sku, ol.qty, o.promised_at, o.order_id FROM order_lines ol JOIN orders o "
                "ON o.order_id = ol.order_id WHERE o.delivered_at IS NULL"):
        inc = incoming.setdefault(r["sku"], {"qty": 0, "eta": None, "order_id": r["order_id"]})
        inc["qty"] += int(_num(r["qty"]))
        inc["eta"] = str(r.get("promised_at") or "") or inc["eta"]
    # orders Sal placed this session (events) that haven't been delivered yet
    evs = all_events()
    delivered = {(e.get("refs") or {}).get("order_id") for e in evs if e.get("type") == "order.delivered"}
    plan_lines: dict[str, list] = {}
    for e in evs:
        d = e.get("data") or {}
        if e.get("type") == "restock.planned":
            plan_lines["last"] = d.get("lines") or []
        if e.get("type") == "order.placed" and (e.get("refs") or {}).get("order_id") not in delivered:
            lines = d.get("lines") or (plan_lines.get("last") if d.get("channel") == "shopify" else None) or []
            for ln in lines:
                if isinstance(ln, dict) and ln.get("sku"):
                    inc = incoming.setdefault(ln["sku"], {"qty": 0, "eta": None, "order_id": None})
                    inc["qty"] += int(_num(ln.get("qty") or ln.get("order_qty"), 1))
                    inc["eta"] = d.get("eta") or inc["eta"]
                    inc["order_id"] = (e.get("refs") or {}).get("order_id")
    out = []
    for it in items:
        qty, mn, mx = int(_num(it["qty"])), int(_num(it["min_qty"])), int(_num(it["max_qty"]))
        nd = need.get(it["sku"], 0)
        status = "out" if qty <= 0 else "low" if qty < mn or qty < nd else "ok"
        out.append({**it, "qty": qty, "min_qty": mn, "max_qty": mx, "needed_7d": nd,
                    "incoming": incoming.get(it["sku"]), "status": status})
    # stock.low events for skus the DB doesn't know (e.g. fixture skus)
    known = {i["sku"] for i in out}
    for e in evs:
        if e.get("type") == "stock.low":
            sku = (e.get("refs") or {}).get("sku")
            if sku and sku not in known:
                d = e.get("data") or {}
                known.add(sku)
                out.append({"sku": sku, "name": e["summary"].split(":")[0], "part_type": "", "qty": d.get("have", 0),
                            "min_qty": None, "max_qty": None, "needed_7d": d.get("need", 0),
                            "incoming": incoming.get(sku), "status": "low" if d.get("have") else "out"})
    return {"items": out, "today": today.isoformat(), "seed": _seed_state}


# ------------------------------------------------------------------ orders
def _order_status(placed, promised, delivered, ref_now) -> str:
    if delivered:
        return "late" if promised and delivered > promised else "delivered"
    if promised and promised < ref_now:
        return "late"
    return "in transit" if placed else "planned"


@router.get("/orders")
def orders(limit: int = 300):
    ref_now = now()
    vendors = {v["vendor_id"]: v["name"] for v in _q("SELECT vendor_id, name FROM vendors")}
    lines: dict[str, list] = {}
    for ln in _q("SELECT order_id, sku, brand, part_type, qty, unit_price FROM order_lines"):
        lines.setdefault(ln["order_id"], []).append(ln)
    out, ids = [], set()
    evs = all_events()
    ev_delivered = {(e.get("refs") or {}).get("order_id"): e for e in evs if e.get("type") == "order.delivered"}
    for e in reversed(evs):
        if e.get("type") != "order.placed":
            continue
        r, d, m = e.get("refs") or {}, e.get("data") or {}, e.get("money") or {}
        oid = str(r.get("order_id") or e["id"])
        if oid in ids:
            continue
        ids.add(oid)
        admin = d.get("admin_url") or next((s.get("url") for s in e.get("sources") or []
                                            if s.get("name") == "Shopify" and s.get("url")), None)
        dl = ev_delivered.get(oid)
        late = bool(dl and ((dl.get("data") or {}).get("on_time") is False or (dl.get("data") or {}).get("late")))
        out.append({"order_id": oid, "placed_at": e["ts"], "vendor_id": r.get("vendor_id"),
                    "vendor": vendors.get(r.get("vendor_id"), r.get("vendor_id")),
                    "channel": d.get("channel") or ("shopify" if admin else "counter"),
                    "items": e["summary"], "total": m.get("wholesale"), "ro_id": r.get("ro_id"),
                    "status": "late" if late else "delivered" if dl else "in transit",
                    "eta": d.get("eta"), "admin_url": admin, "source": "sal"})
    for o in _q("SELECT order_id, vendor_id, ro_id, placed_at, promised_at, delivered_at, total, channel, "
                "external_ref FROM orders ORDER BY placed_at DESC LIMIT %s", [int(limit)]):
        if o["order_id"] in ids:
            continue
        ls = lines.get(o["order_id"], [])
        items = ", ".join(f"{int(_num(x['qty']))}× {x['brand']} {str(x['part_type']).replace('_', ' ')}" for x in ls)
        out.append({"order_id": o["order_id"], "placed_at": str(o["placed_at"]), "vendor_id": o["vendor_id"],
                    "vendor": vendors.get(o["vendor_id"], o["vendor_id"]), "channel": o.get("channel") or "counter",
                    "items": items or "—", "total": _num(o["total"]), "ro_id": o.get("ro_id"),
                    "status": _order_status(_dt(o["placed_at"]), _dt(o["promised_at"]), _dt(o["delivered_at"]), ref_now),
                    "eta": str(o.get("promised_at") or ""), "admin_url": None, "source": "history"})
    planned = [e for e in evs if e.get("type") == "restock.planned"]
    upcoming = []
    if planned:
        last = planned[-1]
        placed_after = any(e.get("type") == "order.placed" and e["ts"] >= last["ts"] for e in evs)
        if not placed_after:
            upcoming.append({"title": last["summary"], "ts": last["ts"], "reason": last.get("reason")})
    out.sort(key=lambda o: str(o["placed_at"]), reverse=True)
    return {"orders": out[:limit], "upcoming": upcoming, "today": ref_now.isoformat()}


# ------------------------------------------------------------------ jobs
def _split_complaint(c: str) -> tuple[str, str]:
    if c and ": " in c:
        v, rest = c.split(": ", 1)
        return v, rest
    return "", c or ""


@router.get("/jobs")
def jobs(limit: int = 200):
    custs = {c["customer_id"]: c["name"] for c in _q("SELECT customer_id, name FROM customers")}
    cost: dict[str, float] = {}
    for o in _q("SELECT ro_id, total FROM orders WHERE ro_id IS NOT NULL"):
        cost[o["ro_id"]] = cost.get(o["ro_id"], 0) + _num(o["total"])
    out, ids = [], set()
    evs = all_events()
    by_ro: dict[str, list] = {}
    for e in evs:
        ro = (e.get("refs") or {}).get("ro_id")
        if ro:
            by_ro.setdefault(ro, []).append(e)
    for ro, es in by_ro.items():
        ros = [e for e in es if e["type"] == "repair_order.created"]
        created = next((e for e in ros if (e.get("data") or {}).get("vehicle")), ros[0] if ros else es[0])
        d = created.get("data") or {}
        spend = sum(_num((e.get("money") or {}).get("wholesale")) for e in es if e["type"] == "order.placed")
        retail = sum(_num((e.get("money") or {}).get("retail")) or markup(_num((e.get("money") or {}).get("wholesale")))
                     for e in es if e["type"] == "order.placed")
        parts = [e["summary"] for e in es if e["type"] == "part.chosen"]
        status = ("done" if any(e["type"] in ("order.delivered", "payment.recorded") for e in es)
                  else "waiting on owner" if any(e["type"] == "escalation" for e in es) else "in progress")
        ids.add(ro)
        out.append({"ro_id": ro, "opened_at": created["ts"], "vehicle": d.get("vehicle") or created["summary"][:40],
                    "complaint": created["summary"], "dtc": d.get("dtc"), "bay": d.get("bay"),
                    "customer": custs.get(d.get("customer_id"), d.get("customer")), "parts": parts,
                    "cost": round(spend, 2), "retail": round(retail, 2), "status": status, "source": "sal",
                    "events": len(es)})
    for r in _q("SELECT ro_id, opened_at, vin, dtc, complaint, bay, customer_id, status FROM repair_orders "
                "ORDER BY opened_at DESC LIMIT %s", [int(limit)]):
        if r["ro_id"] in ids:
            continue
        v, what = _split_complaint(str(r.get("complaint") or ""))
        c = cost.get(r["ro_id"], 0)
        out.append({"ro_id": r["ro_id"], "opened_at": str(r["opened_at"]), "vehicle": v, "complaint": what,
                    "dtc": r.get("dtc") if r.get("dtc") not in (None, "None") else None, "bay": r.get("bay"),
                    "customer": custs.get(r.get("customer_id")), "parts": [], "cost": round(c, 2),
                    "retail": markup(c) if c else 0, "status": r.get("status") or "closed", "source": "history",
                    "events": 0})
    out.sort(key=lambda j: str(j["opened_at"]), reverse=True)
    return {"jobs": out[:limit]}


@router.get("/jobs/{ro_id}")
def job(ro_id: str):
    evs = [e for e in all_events() if (e.get("refs") or {}).get("ro_id") == ro_id]
    row = next((j for j in jobs(1000)["jobs"] if j["ro_id"] == ro_id), None)
    if not row and not evs:
        raise HTTPException(404, "no such job")
    orders_ = _q("SELECT order_id, vendor_id, placed_at, promised_at, delivered_at, total, channel FROM orders "
                 "WHERE ro_id = %s", [ro_id])
    lines = []
    for o in orders_:
        lines += _q("SELECT order_id, sku, brand, part_type, qty, unit_price FROM order_lines WHERE order_id = %s",
                    [o["order_id"]])
    listings = next(((e.get("data") or {}).get("listings") for e in evs if e["type"] == "vendors.compared"
                     and isinstance((e.get("data") or {}).get("listings"), list)), [])
    decisions = {}
    for e in evs:
        if e["type"] in ("part.rejected", "part.chosen"):
            sku = (e.get("refs") or {}).get("sku") or e["id"]
            decisions[sku] = {"verdict": "rejected" if e["type"] == "part.rejected" else "chosen",
                              "summary": e["summary"], "reason": e.get("reason"), "sources": e.get("sources") or []}
    return {"job": row, "events": evs, "orders": orders_, "lines": lines, "listings": listings,
            "decisions": decisions}


# ------------------------------------------------------------------ vendors
@router.get("/vendors")
def vendors(days: int = 90):
    vs = _q("SELECT vendor_id, name, kind, cutoff_local, free_ship_threshold, account_terms FROM vendors")
    cutoff = (now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    try:
        from tools.impl import SCORECARD_SQL
        sql = SCORECARD_SQL.format(filters="")
    except Exception:  # noqa: BLE001
        sql = ""
    score = {r["vendor_id"]: r for r in (_q(sql, [cutoff]) if sql else [])}
    out = []
    for v in vs:
        s = score.get(v["vendor_id"], {})
        out.append({**v, "orders": int(_num(s.get("orders"))), "late": int(_num(s.get("late"))),
                    "late_rate": _num(s.get("late_rate")), "on_time_pct": round(100 * (1 - _num(s.get("late_rate"))), 1)
                    if s else None, "missed_core_credits": int(_num(s.get("missed_core_credits"))),
                    "missed_core_amount": _num(s.get("missed_core_amount")),
                    "avg_price_index": _num(s.get("avg_price_index"), None) if s else None})
    rules = _q("SELECT rule_id, title, rule_text, status, created_at FROM rules ORDER BY rule_id")
    evs = all_events()
    rule_ids = {r["rule_id"] for r in rules}
    for e in evs:
        if e.get("type") in ("rule.proposed", "rule.approved"):
            rid = (e.get("refs") or {}).get("rule_id")
            title = (e.get("data") or {}).get("title") or e["summary"]
            existing = next((r for r in rules if r["rule_id"] == rid), None)
            if existing:
                existing["status"] = "active" if e["type"] == "rule.approved" else existing["status"]
            elif rid:
                rule_ids.add(rid)
                rules.append({"rule_id": rid, "title": title, "rule_text": e.get("reason") or e["summary"],
                              "status": "active" if e["type"] == "rule.approved" else "proposed",
                              "created_at": e["ts"], "learned": True})
    gate = next(((e.get("data") or {}) for e in reversed(evs) if e.get("type") == "gate.enabled"), None)
    return {"vendors": out, "rules": rules, "gate": gate, "sql": sql, "days": days}


# ------------------------------------------------------------------ activity + trace
@router.get("/activity")
def activity():
    chats: dict[str, list] = {}
    actions: dict[str, dict] = {}
    for e in all_events():
        d = e.get("data") or {}
        if e.get("type") == "chat.message":
            cid = str(d.get("chat_id") or "chat")
            chats.setdefault(cid, []).append({"id": e["id"], "ts": e["ts"], "actor": e["actor"],
                                              "text": d.get("text") or e["summary"], "intent": d.get("intent"),
                                              "channel": d.get("channel", "telegram")})
        elif e.get("type") == "action.status":
            aid = str(d.get("action_id") or e["id"])
            a = actions.setdefault(aid, {"action_id": aid, "kind": d.get("kind"), "title": d.get("title") or e["summary"],
                                          "refs": {}, "history": []})
            a["status"] = d.get("status")
            a["updated"] = e["ts"]
            a["refs"].update(e.get("refs") or {})
            a["history"].append({"ts": e["ts"], "status": d.get("status"), "summary": e["summary"]})
    threads = [{"chat_id": k, "messages": v, "last": v[-1]["ts"]} for k, v in chats.items()]
    threads.sort(key=lambda t: t["last"], reverse=True)
    acts = sorted(actions.values(), key=lambda a: a.get("updated", ""), reverse=True)
    return {"threads": threads, "actions": acts}


@router.get("/trace")
def trace(ro_id: str | None = None, order_id: str | None = None, type: str | None = None, q: str | None = None,
          limit: int = 500):
    out = []
    for e in reversed(all_events()):
        r = e.get("refs") or {}
        if ro_id and r.get("ro_id") != ro_id:
            continue
        if order_id and r.get("order_id") != order_id:
            continue
        if type and not str(e.get("type", "")).startswith(type):
            continue
        if q and q.lower() not in json.dumps(e).lower():
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return {"events": out}


@router.get("/home")
def home():
    evs = all_events()
    ref = now()
    week_start = (ref - timedelta(days=ref.weekday())).replace(hour=0, minute=0, second=0)
    spend = retail_ro = cost_ro = saved = 0.0
    for e in evs:
        ts = _dt(e.get("ts"))
        if not ts or ts < week_start:
            continue
        m, d = e.get("money") or {}, e.get("data") or {}
        if e["type"] == "order.placed":
            w = _num(m.get("wholesale"))
            spend += w
            saved += _num(m.get("saved"))
            if (e.get("refs") or {}).get("ro_id") and w:
                cost_ro += w
                retail_ro += _num(m.get("retail")) or markup(w)
        if e["type"] == "escalation" and (d.get("kind") == "dispute_drafted" or d.get("dispute_drafted")):
            saved += _num(m.get("saved"))
    inv = inventory()["items"]
    ords = orders()["orders"]
    arriving = [o for o in ords if o["status"] in ("in transit",)]
    return {"today": ref.isoformat(), "week_start": week_start.isoformat(),
            "money": {"spend": round(spend, 2), "margin_pct": round(100 * (retail_ro - cost_ro) / retail_ro, 1)
                      if retail_ro else None, "saved": round(saved, 2)},
            "low_stock": sum(1 for i in inv if i["status"] != "ok"), "out_of_stock": sum(1 for i in inv if i["status"] == "out"),
            "arriving": arriving[:8], "actions": activity()["actions"][:12],
            "open_jobs": [j for j in jobs(50)["jobs"] if j["status"] not in ("closed", "done")][:6]}


# ------------------------------------------------------------------ integrations
SPONSORS = [("SIE", "sie"), ("Senso", "senso"), ("Persona", "persona"), ("Airbyte", "airbyte"), ("Shopify", "shopify"),
            ("Cognee", "cognee"), ("Statsig", "statsig_client"), ("Amplitude", "amplitude"), ("NHTSA", "nhtsa")]


@router.get("/integrations")
def integrations():
    seen: dict[str, dict] = {}
    for e in all_events():
        for s in e.get("sources") or []:
            n = s.get("name")
            if n:
                x = seen.setdefault(n, {"count": 0, "last": None})
                x["count"] += 1
                x["last"] = e["ts"]
    rows = []
    for name, mod in SPONSORS:
        key = None
        try:
            m = __import__(f"tools.integrations.{mod}", fromlist=["available"])
            key = bool(m.available()) if name != "NHTSA" else True
        except Exception:  # noqa: BLE001
            key = None
        rows.append({"name": name, "key": key, "mode": "live" if key else "fallback" if key is False else "unknown",
                     "events": seen.get(name, {}).get("count", 0), "last": seen.get(name, {}).get("last")})
    try:
        from db import client
        db_backend = client.backend_name()
    except Exception:  # noqa: BLE001
        db_backend = "unavailable"
    rows.insert(0, {"name": "SingleStore", "key": db_backend == "singlestore",
                    "mode": "live" if db_backend == "singlestore" else f"fallback ({db_backend})",
                    "events": seen.get("SingleStore", {}).get("count", 0), "last": seen.get("SingleStore", {}).get("last")})
    return {"integrations": rows, "seed": _seed_state, "demo_mode": os.environ.get("DEMO_MODE", "live")}
