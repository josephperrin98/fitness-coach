"""The plan object: a structured, versioned description of training weeks.

The plan is data, not conversation history. Anything the system must not get
wrong lives here and is checked by the validator.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

WEEK_TYPES = ("foundation", "build", "race_specific", "recovery", "taper", "race")
LOADING_TYPES = ("foundation", "build", "race_specific")
GOALS = ("half", "marathon")
SESSION_KINDS = ("easy", "quality", "long", "test", "football", "strength")
RUN_KINDS = ("easy", "quality", "long", "test")
HARD_KINDS = ("quality", "test")   # count towards Week.quality
UNITS = ("min", "km")
PACE_KINDS = ("easy", "long", "threshold", "interval", "race")   # seconds come from VDOT (D29)


@dataclass(frozen=True)
class Session:
    """One planned session. target is in unit; 0 means "do it", with no size to hit."""
    day: date
    kind: str              # one of SESSION_KINDS
    target: float = 0.0
    unit: str = "min"      # minutes for most sessions, km for the long run
    zone_max: int | None = None   # heart-rate zone ceiling for easy running
    note: str = ""
    pace: str | None = None   # one of PACE_KINDS; the band in s/km is computed, never stored
    structure: str = ""       # e.g. "3 x 10 min"

    def __post_init__(self) -> None:
        if self.kind not in SESSION_KINDS:
            raise ValueError(f"unknown session kind {self.kind!r}; expected one of {SESSION_KINDS}")
        if self.unit not in UNITS:
            raise ValueError(f"unknown unit {self.unit!r}; expected one of {UNITS}")
        if self.pace is not None and self.pace not in PACE_KINDS:
            raise ValueError(f"unknown pace {self.pace!r}; expected one of {PACE_KINDS}")
        if self.target < 0:
            raise ValueError("target must be non-negative")

    @property
    def is_run(self) -> bool:
        return self.kind in RUN_KINDS


@dataclass(frozen=True)
class Week:
    start: date            # Monday
    type: str              # one of WEEK_TYPES
    runs: int
    km: float
    quality: int = 0       # hard sessions (intervals, tempo, race pace)
    long_run_km: float = 0.0
    football: int = 0
    life_event: bool = False   # travel, illness, holiday... overlay on any type
    sessions: tuple[Session, ...] = ()   # optional day-by-day detail

    def __post_init__(self) -> None:
        if self.type not in WEEK_TYPES:
            raise ValueError(f"unknown week type {self.type!r}; expected one of {WEEK_TYPES}")
        if self.runs < 0 or self.km < 0 or self.quality < 0 or self.football < 0:
            raise ValueError("runs, km, quality and football must be non-negative")
        if self.sessions:
            self._check_sessions()

    def _check_sessions(self) -> None:
        # The validator reads the weekly totals, so the sessions must not tell a different story.
        end = self.start + timedelta(days=6)
        for x in self.sessions:
            if not self.start <= x.day <= end:
                raise ValueError(f"session on {x.day} is outside the week starting {self.start}")
        counts = {
            "runs": (len(self.run_sessions), self.runs),
            "quality": (sum(x.kind in HARD_KINDS for x in self.sessions), self.quality),
            "football": (sum(x.kind == "football" for x in self.sessions), self.football),
        }
        for name, (found, declared) in counts.items():
            if found != declared:
                raise ValueError(f"week {self.start}: {found} {name} sessions but the week says {declared}")

    @property
    def run_sessions(self) -> tuple[Session, ...]:
        return tuple(x for x in self.sessions if x.is_run)


@dataclass(frozen=True)
class Plan:
    goal: str                  # "half" | "marathon"
    race_date: date
    weeks: tuple[Week, ...]
    target_time: int | None = None   # race goal in seconds; sets the target VDOT

    def __post_init__(self) -> None:
        if self.goal not in GOALS:
            raise ValueError(f"unknown goal {self.goal!r}; expected one of {GOALS}")
        starts = [w.start for w in self.weeks]
        if starts != sorted(starts):
            raise ValueError("weeks must be in chronological order")

    def week_of(self, day: date) -> Week | None:
        for w in self.weeks:
            if w.start <= day <= w.start + timedelta(days=6):
                return w
        return None

    def sessions_on(self, day: date) -> tuple[Session, ...]:
        w = self.week_of(day)
        return tuple(x for x in w.sessions if x.day == day) if w else ()


def plan_from_dict(data: dict[str, Any]) -> Plan:
    weeks = tuple(
        Week(
            start=_as_date(w["start"]),
            type=w["type"],
            runs=int(w["runs"]),
            km=float(w["km"]),
            quality=int(w.get("quality", 0)),
            long_run_km=float(w.get("long_run_km", 0)),
            football=int(w.get("football", 0)),
            life_event=bool(w.get("life_event", False)),
            sessions=tuple(_session_from_dict(x) for x in w.get("sessions", [])),
        )
        for w in data["weeks"]
    )
    target = data.get("target_time")
    return Plan(goal=data["goal"], race_date=_as_date(data["race_date"]), weeks=weeks,
                target_time=_as_seconds(target) if target else None)


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {
        "goal": plan.goal,
        "race_date": plan.race_date.isoformat(),
        "target_time": _hms(plan.target_time) if plan.target_time else None,
        "weeks": [
            {
                "start": w.start.isoformat(),
                "type": w.type,
                "runs": w.runs,
                "km": w.km,
                "quality": w.quality,
                "long_run_km": w.long_run_km,
                "football": w.football,
                "life_event": w.life_event,
                "sessions": [_session_to_dict(x) for x in w.sessions],
            }
            for w in plan.weeks
        ],
    }


def load_plan(path: str | Path) -> Plan:
    with open(path, encoding="utf-8") as fh:
        return plan_from_dict(yaml.safe_load(fh))


def _session_from_dict(d: dict[str, Any]) -> Session:
    zone = d.get("zone_max")
    return Session(day=_as_date(d["day"]), kind=d["kind"], target=float(d.get("target", 0)),
                   unit=d.get("unit", "min"), zone_max=int(zone) if zone is not None else None,
                   note=str(d.get("note", "")), pace=d.get("pace"), structure=str(d.get("structure", "")))


def _session_to_dict(x: Session) -> dict[str, Any]:
    return {"day": x.day.isoformat(), "kind": x.kind, "target": x.target, "unit": x.unit,
            "zone_max": x.zone_max, "note": x.note, "pace": x.pace, "structure": x.structure}


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _as_seconds(value: Any) -> int:
    """'1:30:00' or '45:00' to seconds."""
    seconds = 0
    for part in str(value).split(":"):
        seconds = seconds * 60 + int(part)
    return seconds


def _hms(seconds: int) -> str:
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
