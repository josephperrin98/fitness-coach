"""A synthetic athlete, so the dashboard can be shown without anyone's real data (D22).

Everything here is made up: the plan, the runs, the recoveries. The numbers go
through the same code as real data (score_week, views.dashboard), so the demo page
shows what the real one would, and the public repo stays free of health data.

    python -m coach demo-data          # writes dashboard/demo-data.json
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .checkins import CheckIn, CheckInStore
from .plan import Plan, Session, Week
from .score import Actual
from .views import dashboard

DEMO_TODAY = date(2026, 12, 9)      # a Wednesday, so the current week is half done
FIRST_MONDAY = date(2026, 10, 19)
SEED = 19                           # fixed, so the file only changes when the code does

# (type, runs, km, quality, long_run_km, football) per week, as in examples/plan.example.yaml
WEEKS = [
    ("foundation", 3, 18, 0, 8, 1), ("foundation", 3, 20, 0, 9, 0),
    ("foundation", 3, 22, 1, 10, 1), ("foundation", 3, 24, 1, 11, 0),
    ("recovery", 3, 14, 0, 7, 0), ("foundation", 3, 21, 0, 9, 1),
    ("foundation", 4, 24, 1, 10, 0), ("foundation", 4, 26, 1, 11, 1),
    ("foundation", 4, 28, 1, 12, 0), ("recovery", 3, 16, 0, 8, 0),
]
EASY_PACE = 6.0                     # min/km, to turn easy kilometres into minutes
CHECKINS = [
    CheckIn(date(2026, 11, 9), "rest", "caution area 4/10: gate says stop", caution_score=4, feel=5),
    CheckIn(date(2026, 11, 30), "modify", "recovery 28%, short sleep", caution_score=1, feel=4, adjusted_target=20),
    CheckIn(DEMO_TODAY, "go", "recovery 71%, caution 0/10", caution_score=0, feel=8),
]


def demo_plan() -> Plan:
    weeks = []
    for i, (kind, runs, km, quality, long_km, football) in enumerate(WEEKS):
        mon = FIRST_MONDAY + timedelta(weeks=i)
        easy_min = round((km - long_km) / (runs - 1) * EASY_PACE / 5) * 5
        sessions = [Session(mon, "easy", easy_min, zone_max=2)]
        sessions.append(Session(mon + timedelta(days=2), "quality", 50, note="6 x 3 min at threshold")
                        if quality else Session(mon + timedelta(days=2), "easy", easy_min, zone_max=2))
        if runs == 4:
            sessions.append(Session(mon + timedelta(days=3), "easy", easy_min - 10, zone_max=2))
        if football:
            sessions.append(Session(mon + timedelta(days=4), "football", 90))
        sessions.append(Session(mon + timedelta(days=6), "long", long_km, unit="km", zone_max=2))
        weeks.append(Week(start=mon, type=kind, runs=runs, km=km, quality=quality,
                          long_run_km=long_km, football=football, sessions=tuple(sessions)))
    return Plan(goal="half", race_date=date(2027, 3, 14), weeks=tuple(weeks))


def demo_actuals(plan: Plan, today: date = DEMO_TODAY, seed: int = SEED) -> list[Actual]:
    """Mostly on plan, with the usual mess: short runs, a missed one, a moved one, an extra gym day."""
    rng = random.Random(seed)
    agreed = {c.day: c for c in CHECKINS}
    out = []
    for w in plan.weeks:
        for s in w.sessions:
            c = agreed.get(s.day)
            if s.day >= today or (c and c.decision == "rest"):
                continue
            if c and c.decision == "modify" and s.is_run:   # did the smaller session that was agreed
                out.append(_actual(s, s.day, c.adjusted_target / s.target, rng))
                continue
            roll = rng.random()
            if roll < 0.06:
                continue                                    # missed
            day = s.day + timedelta(days=1) if roll < 0.11 else s.day   # moved to the next day
            ratio = 0.72 if roll < 0.2 else rng.gauss(1.0, 0.07)       # short, or near target
            out.append(_actual(s, day, ratio, rng))
        gym = w.start + timedelta(days=1)
        if gym < today and rng.random() < 0.5:
            out.append(Actual(gym, "strength", 45, 0, None, datetime.combine(gym, time(18, 30)),
                              round(rng.uniform(6, 9), 1)))
    return out


def _actual(s: Session, day: date, ratio: float, rng: random.Random) -> Actual:
    start = datetime.combine(day, time(19, 0) if s.kind == "football" else time(7, 15))
    if s.kind == "football":
        return Actual(day, "football", round(s.target * ratio), 0, None, start, round(rng.uniform(13, 17), 1))
    if s.unit == "km":
        km = round(s.target * ratio, 2)
        minutes = round(km * EASY_PACE * rng.uniform(0.96, 1.04), 1)
    else:
        minutes = round(s.target * ratio, 1)
        km = round(minutes / (4.9 if s.kind == "quality" else EASY_PACE), 2)
    drift = rng.uniform(0.0, 0.3) if s.zone_max else 0.0       # easy runs that crept into zone 3
    zones = ({2: round(minutes * (1 - drift), 1), 3: round(minutes * drift, 1)} if s.zone_max
             else {2: round(minutes * 0.5, 1), 4: round(minutes * 0.5, 1)})
    strain = round(8 + minutes / 12 + (3 if s.kind == "quality" else 0), 1)
    return Actual(day, "run", minutes, km, zones, start, strain)


def demo_recoveries(actuals: list[Actual], start: date, end: date, seed: int = SEED) -> list[dict]:
    """Next-morning HRV drops after hard days, so the 'what it costs you' view has a story."""
    rng = random.Random(seed + 1)
    strain_by_day: dict[date, float] = {}
    for a in actuals:
        strain_by_day[a.day] = strain_by_day.get(a.day, 0) + (a.strain or 0)
    out, d = [], start
    while d <= end:
        load = strain_by_day.get(d - timedelta(days=1), 0)
        hrv = round(max(35.0, rng.gauss(72, 5) - 1.1 * max(0.0, load - 8)), 1)
        recovery = round(min(99, max(5, (hrv - 40) * 2.1 + rng.gauss(0, 6))))
        out.append({"date": d.isoformat(), "recovery": recovery, "hrv": hrv, "resting_hr": round(rng.gauss(48, 2))})
        d += timedelta(days=1)
    return out


def demo_checkins(plan: Plan) -> CheckInStore:
    store = CheckInStore(":memory:")
    for c in CHECKINS:
        store.record(c, plan)
    return store


def demo_dashboard(today: date = DEMO_TODAY) -> dict[str, Any]:
    plan = demo_plan()
    actuals = demo_actuals(plan, today)
    recoveries = demo_recoveries(actuals, FIRST_MONDAY, today)
    out = dashboard(plan, demo_checkins(plan), actuals, recoveries, today, weeks_back=8, weeks_ahead=2)
    out["demo"] = True
    return out


def write_demo(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(demo_dashboard(), indent=1, default=str) + "\n", encoding="utf-8")
    return path
