"""Simulated shop clock for the demo week Mon Nov 16 - Sun Nov 22 2026 (America/Los_Angeles, PST)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

PST = timezone(timedelta(hours=-8), "PST")

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WEEK_ORDER = ("mon", "tue", "wed", "fri", "sun")  # days the demo actually runs

# Start time of each day-run (contracts/demo_script.md; TUE is the D-006 escalation beat).
DAY_START = {
    "mon": (9, 12),
    "tue": (10, 5),
    "wed": (7, 30),
    "fri": (16, 0),
    "sun": (18, 0),
}

WEEK_MONDAY = datetime(2026, 11, 16, tzinfo=PST)


def day_date(day: str) -> datetime:
    if day not in DAYS:
        raise ValueError(f"unknown day {day!r}")
    return WEEK_MONDAY + timedelta(days=DAYS.index(day))


def day_start(day: str) -> datetime:
    h, m = DAY_START.get(day, (8, 0))
    return day_date(day).replace(hour=h, minute=m)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


@dataclass
class SimClock:
    """Monotonic simulated clock. `advance` moves shop time; never goes backwards."""

    day: str
    now: datetime = field(default=None)  # type: ignore[assignment]

    def __post_init__(self):
        if self.now is None:
            self.now = day_start(self.day)

    def advance(self, minutes: float = 0, seconds: float = 0) -> datetime:
        self.now = self.now + timedelta(minutes=minutes, seconds=seconds)
        return self.now

    def advance_to(self, dt: datetime) -> datetime:
        if dt > self.now:
            self.now = dt
        return self.now

    def at(self, hour: int, minute: int = 0) -> datetime:
        return self.now.replace(hour=hour, minute=minute, second=0)

    def iso(self) -> str:
        return iso(self.now)


def next_day(day: str | None) -> str | None:
    """Next day in the demo week order; None after Sunday. `None` input -> Monday."""
    if day is None:
        return WEEK_ORDER[0]
    i = WEEK_ORDER.index(day)
    return WEEK_ORDER[i + 1] if i + 1 < len(WEEK_ORDER) else None
