"""The plan object: a structured, versioned description of training weeks.

The plan is data, not conversation history. Anything the system must not get
wrong lives here and is checked by the validator.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

WEEK_TYPES = ("foundation", "build", "race_specific", "recovery", "taper", "race")
LOADING_TYPES = ("foundation", "build", "race_specific")
GOALS = ("half", "marathon")


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

    def __post_init__(self) -> None:
        if self.type not in WEEK_TYPES:
            raise ValueError(f"unknown week type {self.type!r}; expected one of {WEEK_TYPES}")
        if self.runs < 0 or self.km < 0 or self.quality < 0 or self.football < 0:
            raise ValueError("runs, km, quality and football must be non-negative")


@dataclass(frozen=True)
class Plan:
    goal: str                  # "half" | "marathon"
    race_date: date
    weeks: tuple[Week, ...]

    def __post_init__(self) -> None:
        if self.goal not in GOALS:
            raise ValueError(f"unknown goal {self.goal!r}; expected one of {GOALS}")
        starts = [w.start for w in self.weeks]
        if starts != sorted(starts):
            raise ValueError("weeks must be in chronological order")


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
        )
        for w in data["weeks"]
    )
    return Plan(goal=data["goal"], race_date=_as_date(data["race_date"]), weeks=weeks)


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {
        "goal": plan.goal,
        "race_date": plan.race_date.isoformat(),
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
            }
            for w in plan.weeks
        ],
    }


def load_plan(path: str | Path) -> Plan:
    with open(path, encoding="utf-8") as fh:
        return plan_from_dict(yaml.safe_load(fh))


def _as_date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))
