"""Human actors in the sim: shop owner + car owner.

Auto mode: approve after a small real-time delay. Interactive mode: block until someone POSTs
/sim/approve {kind, id} (the UI button, proxied by ui/server to sim.api on :8102).

Other streams can call `request(kind, id)` + `wait(kind, id)` in-process, or poll GET /sim/approvals.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

KINDS = ("quote", "order", "rule", "identity")


@dataclass
class Approval:
    kind: str
    id: str
    actor: str  # owner | car_owner
    summary: str = ""
    status: str = "pending"  # pending | approved | declined
    requested_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    event: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict:
        return {"kind": self.kind, "id": self.id, "actor": self.actor, "summary": self.summary,
                "status": self.status}


class Actors:
    def __init__(self, interactive: bool = False, delay_s: float | None = None):
        self.interactive = interactive
        self.delay_s = float(os.getenv("SIM_APPROVE_DELAY", "1.0")) if delay_s is None else delay_s
        self._lock = threading.Lock()
        self._items: dict[tuple[str, str], Approval] = {}

    def request(self, kind: str, id: str, actor: str = "owner", summary: str = "") -> Approval:
        with self._lock:
            a = self._items.get((kind, id))
            if a is None:
                a = Approval(kind=kind, id=id, actor=actor, summary=summary)
                self._items[(kind, id)] = a
            return a

    def decide(self, kind: str, id: str, approved: bool = True) -> Approval | None:
        with self._lock:
            a = self._items.get((kind, id))
            if a is None:  # UI may approve before the sim asks; record it
                a = Approval(kind=kind, id=id, actor="owner")
                self._items[(kind, id)] = a
        a.status = "approved" if approved else "declined"
        a.decided_at = time.time()
        a.event.set()
        return a

    def wait(self, kind: str, id: str, timeout: float = 600.0) -> str:
        """Block until decided. Auto mode approves after `delay_s`."""
        a = self.request(kind, id)
        if not self.interactive:
            if not a.event.wait(self.delay_s):
                self.decide(kind, id, True)
            return a.status
        if not a.event.wait(timeout):
            return "pending"
        return a.status

    def pending(self) -> list[dict]:
        with self._lock:
            return [a.public() for a in self._items.values() if a.status == "pending"]

    def all(self) -> list[dict]:
        with self._lock:
            return [a.public() for a in self._items.values()]


# Process-wide singleton so sim.api and sim.run share approvals.
ACTORS = Actors()


def configure(interactive: bool, delay_s: float | None = None) -> Actors:
    ACTORS.interactive = interactive
    if delay_s is not None:
        ACTORS.delay_s = delay_s
    return ACTORS


# --- car owner persona (also used by firedrill/) ----------------------------------------------------
CAR_OWNER = {"name": "Dana Ruiz", "customer_id": "cust-dana-ruiz", "auto_approve_max": 150.0}


def car_owner_reply(total: float) -> dict:
    """Dana approves quotes <= $150; otherwise asks exactly one question first."""
    if total <= CAR_OWNER["auto_approve_max"]:
        return {"status": "approved", "text": f"Sounds good, go ahead (${total:.2f})."}
    return {"status": "question",
            "text": f"${total:.2f} is more than I expected. Is there a cheaper part that is just as reliable?"}
