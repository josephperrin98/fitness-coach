"""Fitness as one number, VDOT, and the paces that follow from it (D29, D30).

VDOT is Daniels and Gilbert's model: the oxygen cost of running at a speed,
divided by the fraction of VO2max a runner can hold for that duration. One race
or test result gives a VDOT; every training pace follows from it. Standard
library only: the model is two published equations.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date, timedelta

from .plan import LOADING_TYPES, Week

RACE_METRES = {"half": 21097.5, "marathon": 42195.0}


def _oxygen_cost(metres_per_min: float) -> float:
    return -4.60 + 0.182258 * metres_per_min + 0.000104 * metres_per_min ** 2


def _fraction_held(minutes: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * minutes) + 0.2989558 * math.exp(-0.1932605 * minutes)


def _speed_for_cost(cost: float) -> float:
    # Inverse of _oxygen_cost: the positive root of a*v^2 + b*v + c = 0.
    a, b, c = 0.000104, 0.182258, -4.60 - cost
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def vdot(distance_m: float, seconds: float) -> float:
    minutes = seconds / 60
    return _oxygen_cost(distance_m / minutes) / _fraction_held(minutes)


def race_seconds(vdot_value: float, distance_m: float) -> float:
    """The time a runner with this VDOT is predicted to run the distance in."""
    lo, hi = 60.0, 50_000.0
    for _ in range(100):   # bisection: vdot() falls as the time grows
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if vdot(distance_m, mid) > vdot_value else (lo, mid)
    return (lo + hi) / 2


def pace_band(vdot_value: float, kind: str, intensity: dict, race_m: float | None = None) -> tuple[int, int]:
    """(fast, slow) pace in seconds per km for a session kind."""
    if kind == "race":
        if race_m is None:
            raise ValueError("race pace needs a race distance")
        pace = race_seconds(vdot_value, race_m) / (race_m / 1000)
        return round(pace / 1.01), round(pace / 0.99)
    low, high = intensity[kind]
    return round(60_000 / _speed_for_cost(high * vdot_value)), round(60_000 / _speed_for_cost(low * vdot_value))


def fmt_pace(sec_per_km: float) -> str:
    s = round(sec_per_km)
    return f"{s // 60}:{s % 60:02d}"


def pace_bands(vdot_value: float, intensity: dict, race_m: float | None = None) -> dict[str, str]:
    """Every band as "m:ss-m:ss/km", fast end first; race pace only when there is a race."""
    kinds = ["easy", "long", "threshold", "interval"] + (["race"] if race_m else [])
    return {k: "{}-{}/km".format(*map(fmt_pace, pace_band(vdot_value, k, intensity, race_m))) for k in kinds}


def vdot_line(weeks: Sequence[Week], start_day: date, start_vdot: float,
              target_day: date, target_vdot: float) -> dict[date, float]:
    """Planned VDOT for each week from the checkpoint's week on (D30).

    It rises in equal steps in loading weeks up to the target's week and holds in
    recovery, taper and race weeks, so recovery is never asked to make you fitter.
    """
    first = start_day - timedelta(days=start_day.weekday())
    last = target_day - timedelta(days=target_day.weekday())
    ahead = [w for w in weeks if w.start >= first]
    rising = [w for w in ahead if first < w.start <= last and w.type in LOADING_TYPES]
    step = (target_vdot - start_vdot) / len(rising) if rising and target_vdot > start_vdot else 0.0
    line, value = {}, start_vdot
    for w in ahead:
        if w in rising:
            value += step
        line[w.start] = round(value, 2)
    return line


def pace_vdot(line_vdot: float, checkpoint_vdot: float, cap: float) -> float:
    """The VDOT paces are computed from: the planned line, never more than cap above the last test."""
    return min(line_vdot, checkpoint_vdot + cap)
