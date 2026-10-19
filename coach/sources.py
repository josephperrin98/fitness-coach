"""Turn raw Strava and Whoop rows into Actuals, and join the two.

Strava knows the run (distance, pace, moving time) but usually not the heart rate;
Whoop knows the heart rate but not the route. Joining them by start time is what
lets a run be scored on both volume and intensity.

Inputs are what the connectors return at the moment of the call. Nothing here
writes to disk (D21).
"""
from __future__ import annotations

from datetime import datetime

from .score import Actual

STRAVA_KINDS = {
    "Run": "run", "TrailRun": "run", "VirtualRun": "run",
    "Soccer": "football",
    "WeightTraining": "strength", "Workout": "strength", "Crossfit": "strength",
    "Ride": "ride", "VirtualRide": "ride", "GravelRide": "ride", "MountainBikeRide": "ride",
}
WHOOP_KINDS = {
    "running": "run", "soccer": "football",
    "weightlifting": "strength", "functional-fitness": "strength", "strength-trainer": "strength",
    "cycling": "ride",
}
MATCH_WINDOW_MIN = 30   # same activity if the two starts are this close


def actuals_from_strava(activities: list[dict]) -> list[Actual]:
    out = []
    for a in activities:
        start = datetime.fromisoformat(a["start_local"])
        s = a.get("summary", a)
        out.append(Actual(day=start.date(), kind=STRAVA_KINDS.get(a.get("sport_type"), "other"),
                          minutes=round(s.get("moving_time", 0) / 60, 1),
                          km=round(s.get("distance", 0) / 1000, 2), start=start))
    return out


def actuals_from_whoop(workouts: list[dict]) -> list[Actual]:
    out = []
    for w in workouts:
        start = datetime.fromisoformat(w["start"])
        zones = {int(k): float(v) for k, v in (w.get("zone_minutes") or {}).items()}
        out.append(Actual(day=start.date(), kind=WHOOP_KINDS.get(w.get("sport"), "other"),
                          minutes=float(w.get("minutes") or 0), km=float(w.get("distance_km") or 0),
                          zone_minutes=zones or None, start=start, strain=w.get("strain")))
    return out


def merge(strava: list[Actual], whoop: list[Actual]) -> list[Actual]:
    """Strava rows win on volume; a Whoop row with the same kind and a close start adds
    heart-rate zones and strain. Whoop rows with no Strava twin are kept as they are."""
    unused = list(whoop)
    out = []
    for a in strava:
        twin = _closest(a, unused)
        if twin is not None:
            unused.remove(twin)
            a = Actual(day=a.day, kind=a.kind, minutes=a.minutes, km=a.km or twin.km,
                       zone_minutes=twin.zone_minutes, start=a.start, strain=twin.strain)
        out.append(a)
    return sorted(out + unused, key=lambda x: (x.day, x.start or datetime.min))


def _closest(a: Actual, pool: list[Actual]) -> Actual | None:
    best, gap = None, MATCH_WINDOW_MIN + 1
    for w in pool:
        if w.kind != a.kind or a.start is None or w.start is None:
            continue
        g = abs((w.start - a.start).total_seconds()) / 60
        if g < gap:
            best, gap = w, g
    return best if gap <= MATCH_WINDOW_MIN else None
