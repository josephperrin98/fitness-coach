"""Checkpoints: test results that set the athlete's measured VDOT (D31).

A result usually comes from Strava, and Strava data is never stored (D21). So the
agent shows the numbers and records them only after the athlete confirms them: what
is stored is the athlete's own statement of their result. VDOT is derived on read,
never stored, so a change to the formula can never leave stale numbers behind.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone

from .fitness import vdot

CHECKPOINT_KINDS = ("6min", "5k", "race")

SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    day         TEXT NOT NULL,
    kind        TEXT NOT NULL,
    distance_m  REAL NOT NULL,
    seconds     REAL NOT NULL,
    created_at  TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Checkpoint:
    day: date
    kind: str
    distance_m: float
    seconds: float

    def __post_init__(self) -> None:
        if self.kind not in CHECKPOINT_KINDS:
            raise ValueError(f"unknown checkpoint kind {self.kind!r}; expected one of {CHECKPOINT_KINDS}")
        if not (math.isfinite(self.distance_m) and math.isfinite(self.seconds)
                and self.distance_m > 0 and self.seconds > 0):
            raise ValueError("distance and time must be positive finite numbers")

    @property
    def vdot(self) -> float:
        return vdot(self.distance_m, self.seconds)


class CheckpointStore:
    def __init__(self, path: str = ":memory:") -> None:
        # Same threading note as CheckInStore: one user, calls arrive one at a time.
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def record(self, c: Checkpoint) -> Checkpoint:
        self.db.execute(
            "INSERT INTO checkpoints (day, kind, distance_m, seconds, created_at) VALUES (?,?,?,?,?)",
            (c.day.isoformat(), c.kind, c.distance_m, c.seconds,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        self.db.commit()
        return c

    def latest(self, as_of: date) -> Checkpoint | None:
        row = self.db.execute("SELECT * FROM checkpoints WHERE day <= ? ORDER BY day DESC, id DESC LIMIT 1",
                              (as_of.isoformat(),)).fetchone()
        return Checkpoint(day=date.fromisoformat(row["day"]), kind=row["kind"],
                          distance_m=row["distance_m"], seconds=row["seconds"]) if row else None
