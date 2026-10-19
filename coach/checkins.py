"""Daily check-in records (D18, D20).

A check-in decides today only: go, modify (a smaller session) or rest. It never
touches future days; that is the weekly review, through propose/confirm.

Autonomy scales with risk. The agent records a check-in after the user agrees in
chat, and the code cannot see that chat, so the only changes allowed here are the
ones that make today *easier*. Anything that adds load is refused and has to go
through PlanStore.propose(), where only a human can confirm.

What is stored: the decision, its reason, and the user's own inputs (caution
score, how they feel). Never Strava data (D21).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone

from .plan import Plan
from .score import Adjustment

DECISIONS = ("go", "modify", "rest")

SCHEMA = """
CREATE TABLE IF NOT EXISTS checkins (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    day             TEXT NOT NULL,
    decision        TEXT NOT NULL CHECK (decision IN ('go','modify','rest')),
    reason          TEXT NOT NULL,
    caution_score   INTEGER,
    feel            INTEGER,          -- the user's own 1-10 rating
    note            TEXT NOT NULL DEFAULT '',
    adjusted_target REAL,
    adjusted_unit   TEXT,
    created_at      TEXT NOT NULL
);
"""


class CheckInError(Exception):
    """Raised when a check-in asks for something a check-in may not do."""


@dataclass(frozen=True)
class CheckIn:
    day: date
    decision: str
    reason: str
    caution_score: int | None = None
    feel: int | None = None
    note: str = ""
    adjusted_target: float | None = None
    adjusted_unit: str | None = None

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}, got {self.decision!r}")
        for name in ("caution_score", "feel"):
            v = getattr(self, name)
            if v is not None and not 0 <= v <= 10:
                raise ValueError(f"{name} must be between 0 and 10")


class CheckInStore:
    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def record(self, c: CheckIn, plan: Plan | None) -> CheckIn:
        c = self._check(c, plan)
        self.db.execute(
            "INSERT INTO checkins (day, decision, reason, caution_score, feel, note,"
            " adjusted_target, adjusted_unit, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (c.day.isoformat(), c.decision, c.reason, c.caution_score, c.feel, c.note,
             c.adjusted_target, c.adjusted_unit, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        self.db.commit()
        return c

    def latest(self, day: date) -> CheckIn | None:
        row = self.db.execute("SELECT * FROM checkins WHERE day=? ORDER BY id DESC LIMIT 1",
                              (day.isoformat(),)).fetchone()
        return _from_row(row) if row else None

    def between(self, start: date, end: date) -> list[CheckIn]:
        """The latest check-in of each day in [start, end], oldest first."""
        rows = self.db.execute(
            "SELECT * FROM checkins WHERE id IN (SELECT MAX(id) FROM checkins WHERE day BETWEEN ? AND ?"
            " GROUP BY day) ORDER BY day", (start.isoformat(), end.isoformat())).fetchall()
        return [_from_row(r) for r in rows]

    def adjustments(self, start: date = date.min, end: date = date.max) -> dict[date, Adjustment]:
        out: dict[date, Adjustment] = {}
        for c in self.between(start, end):
            if c.decision == "rest":
                out[c.day] = Adjustment(target=0, unit=c.adjusted_unit or "min", rest=True)
            elif c.decision == "modify":
                out[c.day] = Adjustment(target=c.adjusted_target or 0, unit=c.adjusted_unit or "min")
        return out

    @staticmethod
    def _check(c: CheckIn, plan: Plan | None) -> CheckIn:
        if c.decision == "go":
            if c.adjusted_target is not None:
                raise CheckInError("a 'go' keeps the planned session; use 'modify' to change it")
            return c
        if c.decision == "rest":
            return c
        planned = [s for s in (plan.sessions_on(c.day) if plan else ()) if s.is_run]
        if not planned:
            raise CheckInError(f"no planned run on {c.day} to modify")
        s = planned[0]
        unit = c.adjusted_unit or s.unit
        if unit != s.unit:
            raise CheckInError(f"the planned session is in {s.unit}; give the new target in {s.unit}")
        if c.adjusted_target is None or c.adjusted_target >= s.target:
            raise CheckInError(
                f"a check-in can only make today easier: planned {s.target:g} {s.unit}, "
                f"asked {c.adjusted_target}. To add load, propose a plan change.")
        return CheckIn(**{**c.__dict__, "adjusted_unit": unit})


def _from_row(r: sqlite3.Row) -> CheckIn:
    return CheckIn(day=date.fromisoformat(r["day"]), decision=r["decision"], reason=r["reason"],
                   caution_score=r["caution_score"], feel=r["feel"], note=r["note"],
                   adjusted_target=r["adjusted_target"], adjusted_unit=r["adjusted_unit"])
