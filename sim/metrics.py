"""Metrics per run/variant (S5): on-time %, expected late-penalty cost, escalations, avg cost.

Pure functions over event lists so they're testable; `store()` writes to the `metrics` table via db.client
when available, else runs/<run_id>/metrics.json.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Cost of a late part on a car-on-a-lift job: idle bay + loaner/comp for a missed promise.
LATE_PENALTY_USD = 120.0
ROUTED_PART_TYPES = ("starter", "alternator")

# Planted seed patterns (SPEC §9): Bayshore late 3/8 on starters/alternators; Mission on-time 95%.
DEFAULT_LATE_RATE = {"bayshore": 0.375, "mission": 0.05, "partsdepot": 0.10}
# Starter wholesale prices for the replay job (illustrative; overridden by scorecard data if present).
DEFAULT_STARTER_PRICE = {"bayshore": 148.0, "mission": 163.0}
REPLAY_JOBS = 8


@dataclass
class Metrics:
    variant: str
    jobs: int
    on_time_pct: float
    expected_late_penalty: float
    escalations: float
    avg_cost: float

    def rows(self, run_id: str, day: str) -> list[tuple]:
        return [(run_id, day, self.variant, k, float(v)) for k, v in self.as_dict().items()
                if k != "variant"]

    def as_dict(self) -> dict:
        return {"variant": self.variant, "jobs": self.jobs, "on_time_pct": round(self.on_time_pct, 1),
                "expected_late_penalty": round(self.expected_late_penalty, 2),
                "escalations": round(self.escalations, 2), "avg_cost": round(self.avg_cost, 2)}


def job_metrics(variant: str, vendor_for_job: list[str], price: dict[str, float],
                late_rate: dict[str, float], penalty: float = LATE_PENALTY_USD) -> Metrics:
    """Expected metrics for a list of jobs, each sourced from the given vendor."""
    n = len(vendor_for_job)
    if n == 0:
        return Metrics(variant, 0, 100.0, 0.0, 0.0, 0.0)
    lates = [late_rate.get(v, 0.0) for v in vendor_for_job]
    exp_late = sum(lates)
    return Metrics(
        variant=variant,
        jobs=n,
        on_time_pct=100.0 * (1 - exp_late / n),
        expected_late_penalty=exp_late * penalty,
        escalations=exp_late,  # every late part on a lift job escalates to the owner
        avg_cost=sum(price.get(v, 0.0) for v in vendor_for_job) / n,
    )


def vendor_stats_from_events(events: list[dict]) -> tuple[dict[str, float], dict[str, float]]:
    """Late rates (and prices if present) from the latest scorecard.built event; falls back to seed defaults."""
    late = dict(DEFAULT_LATE_RATE)
    price = dict(DEFAULT_STARTER_PRICE)
    for ev in reversed(events):
        if ev.get("type") != "scorecard.built":
            continue
        for row in (ev.get("data") or {}).get("per_vendor", []) or []:
            vid = row.get("vendor_id")
            if vid and isinstance(row.get("late_rate"), (int, float)):
                late[vid] = float(row["late_rate"])
            if vid and isinstance(row.get("starter_price"), (int, float)):
                price[vid] = float(row["starter_price"])
        break
    return late, price


def replay_starter(gate_on: bool, late: dict[str, float], price: dict[str, float],
                   jobs: int = REPLAY_JOBS) -> Metrics:
    """Gate OFF: `cheapest` picks Bayshore. Gate ON: routing rule sends starters/alternators to Mission."""
    vendor = "mission" if gate_on else min(price, key=price.get)
    return job_metrics("gate_on" if gate_on else "gate_off", [vendor] * jobs, price, late)


def run_metrics(events: list[dict], variant: str) -> Metrics:
    """Observed metrics for one day-run's events."""
    placed = [e for e in events if e.get("type") == "order.placed"]
    delivered = [e for e in events if e.get("type") == "order.delivered"]
    esc = sum(1 for e in events if e.get("type") == "escalation")
    costs = [float(e["money"]["wholesale"]) for e in placed
             if isinstance((e.get("money") or {}).get("wholesale"), (int, float))]
    on_time = [bool((e.get("data") or {}).get("on_time", True)) for e in delivered]
    late_count = sum(1 for x in on_time if not x)
    return Metrics(
        variant=variant,
        jobs=len(placed),
        on_time_pct=100.0 * (sum(on_time) / len(on_time)) if on_time else 100.0,
        expected_late_penalty=late_count * LATE_PENALTY_USD,
        escalations=float(esc),
        avg_cost=(sum(costs) / len(costs)) if costs else 0.0,
    )


def store(run_id: str, day: str, metrics: list[Metrics]) -> str:
    rows = [r for m in metrics for r in m.rows(run_id, day)]
    try:
        from db import client as dbc  # type: ignore

        for fn in ("insert_metrics", "write_metrics"):
            f = getattr(dbc, fn, None)
            if callable(f):
                f(rows)
                return f"db.client.{fn}"
        conn_fn = getattr(dbc, "get_conn", None) or getattr(dbc, "connect", None)
        execute = getattr(dbc, "executemany", None) or getattr(dbc, "execute", None)
        if callable(execute):
            sql = "INSERT INTO metrics (run_id, day, variant, name, value) VALUES (%s, %s, %s, %s, %s)"
            if getattr(dbc, "executemany", None):
                execute(sql, rows)
            else:
                for r in rows:
                    execute(sql, r)
            return "db.client.execute"
        if callable(conn_fn):
            conn = conn_fn()
            cur = conn.cursor()
            cur.executemany("INSERT INTO metrics (run_id, day, variant, name, value) VALUES (%s, %s, %s, %s, %s)",
                            rows)
            conn.commit()
            return "db.client.conn"
    except Exception as e:  # noqa: BLE001
        print(f"[sim] metrics -> db failed ({e!r}); writing json", file=sys.stderr)
    p = ROOT / "runs" / run_id / "metrics.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing += [dict(zip(("run_id", "day", "variant", "name", "value"), r)) for r in rows]
    p.write_text(json.dumps(existing, indent=1), encoding="utf-8")
    return "json"
