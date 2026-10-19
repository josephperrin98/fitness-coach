"""How closely the plan was followed (D17).

Two separate numbers per session, never blended, so it is clear which one slipped:
  adherence  did you do the planned amount, on the planned day
  execution  did you do it at the planned intensity (share of minutes at or below
             the zone ceiling; only when the session has one and heart-rate zones exist)

Actuals come from Strava and Whoop at the moment of the call and are never stored.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .plan import Session, Week
from .rules import RuleSet, load_rules

ACTUAL_KINDS = ("run", "football", "strength", "ride", "other")


@dataclass(frozen=True)
class Actual:
    """One activity that happened, already normalised from its source."""
    day: date
    kind: str                       # one of ACTUAL_KINDS
    minutes: float = 0.0
    km: float = 0.0
    zone_minutes: dict[int, float] | None = None   # Whoop heart-rate zones 0-5
    start_hour: int | None = None


@dataclass(frozen=True)
class Adjustment:
    """A same-day change agreed at the check-in; the session is scored against it."""
    target: float
    unit: str = "min"
    rest: bool = False


@dataclass(frozen=True)
class SessionScore:
    day: date
    kind: str
    planned: float
    unit: str
    status: str              # done | short | over | moved | missed | excused | upcoming
    actual: float = 0.0
    actual_day: date | None = None
    adherence: float | None = None
    execution: float | None = None
    adjusted: bool = False


@dataclass(frozen=True)
class WeekScore:
    start: date
    sessions: tuple[SessionScore, ...]
    adherence: float | None          # mean over scored sessions; None if nothing to score yet
    execution: float | None
    extra: tuple[Actual, ...] = field(default_factory=tuple)   # done but not planned


def adherence(actual: float, target: float, rules: RuleSet | None = None) -> float:
    """r = actual / target. Short: 100 * r. Over: 100 - 50 * (r - 1), floor 0 (rates from rules.yaml)."""
    if target <= 0:
        return 100.0
    p = (rules or load_rules()).scoring["adherence"]
    r = actual / target
    if r <= 1:
        return round(100 * (1 - p["shortfall_rate"] * (1 - r)), 1)
    return round(max(0.0, 100 * (1 - p["overshoot_rate"] * (r - 1))), 1)


def score_week(week: Week, actuals: list[Actual], as_of: date,
               adjustments: dict[date, Adjustment] | None = None,
               rules: RuleSet | None = None) -> WeekScore:
    rules = rules or load_rules()
    penalty = rules.scoring["adherence"]["moved_penalty"]
    adjustments = adjustments or {}

    # Group this week's actuals by (kind family, day); two runs on one day count as one session.
    pool: dict[tuple[str, date], list[Actual]] = {}
    for a in actuals:
        if _in_week(week, a.day):
            pool.setdefault((_family(a.kind), a.day), []).append(a)

    results: list[SessionScore | None] = [None] * len(week.sessions)
    order = sorted(range(len(week.sessions)), key=lambda i: week.sessions[i].day)

    # Pass 1: same-day matches. Pass 2: leftovers on another day of the week count as moved.
    for i in order:
        s = week.sessions[i]
        adj = adjustments.get(s.day)
        if adj and adj.rest:
            results[i] = SessionScore(s.day, s.kind, 0, s.unit, "excused", adjusted=True)
            continue
        key = (_family(s.kind), s.day)
        if key in pool:
            results[i] = _scored(s, pool.pop(key), s.day, adj, 0, rules)
    for i in order:
        if results[i] is not None:
            continue
        s = week.sessions[i]
        family = _family(s.kind)
        others = sorted((k for k in pool if k[0] == family), key=lambda k: abs((k[1] - s.day).days))
        if others:
            results[i] = _scored(s, pool.pop(others[0]), others[0][1], adjustments.get(s.day), penalty, rules)
        elif s.day > as_of:
            results[i] = SessionScore(s.day, s.kind, s.target, s.unit, "upcoming")
        else:
            results[i] = SessionScore(s.day, s.kind, s.target, s.unit, "missed", adherence=0.0)

    done = tuple(r for r in results if r is not None)
    adh = [r.adherence for r in done if r.adherence is not None]
    exe = [r.execution for r in done if r.execution is not None]
    extra = tuple(a for group in pool.values() for a in group)
    return WeekScore(week.start, done, _mean(adh), _mean(exe), extra)


def _scored(s: Session, group: list[Actual], on: date, adj: Adjustment | None,
            penalty: float, rules: RuleSet) -> SessionScore:
    target, unit = (adj.target, adj.unit) if adj else (s.target, s.unit)
    value = sum(a.km if unit == "km" else a.minutes for a in group)
    score = adherence(value, target, rules)
    if penalty:
        status = "moved"
        score = max(0.0, score - penalty)
    elif target <= 0 or abs(value - target) < 1e-9:
        status = "done"
    else:
        status = "short" if value < target else "over"
    return SessionScore(s.day, s.kind, target, unit, status, round(value, 1), on, score,
                        _execution(s, group), adjusted=adj is not None)


def _execution(s: Session, group: list[Actual]) -> float | None:
    if s.zone_max is None:
        return None
    zones: dict[int, float] = {}
    for a in group:
        for z, m in (a.zone_minutes or {}).items():
            zones[int(z)] = zones.get(int(z), 0.0) + m
    total = sum(zones.values())
    if total <= 0:
        return None
    return round(100 * sum(m for z, m in zones.items() if z <= s.zone_max) / total, 1)


def _family(kind: str) -> str:
    # Every run kind in the plan (easy, quality, long, test) matches an actual "run".
    return "run" if kind in ("run", "easy", "quality", "long", "test") else kind


def _in_week(week: Week, d: date) -> bool:
    return 0 <= (d - week.start).days <= 6


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None
