"""What the dashboard shows, computed here so it is tested and the page stays a renderer (D23).

Three views in v0:
  calendar         every day: what was planned, what was done, the score, the
                   check-in decision and that morning's recovery
  weeks            adherence and execution per week, planned vs actual km
  activity_cost    how each kind of activity moves the next morning's HRV and recovery
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from statistics import mean, median
from typing import Any, Callable

from .checkins import CheckInStore
from .plan import Plan
from .rules import RuleSet, load_rules
from .score import Actual, score_week

MIN_SAMPLES = 5   # below this, a view says "not enough data yet" instead of drawing a conclusion


def dashboard(plan: Plan | None, checkins: CheckInStore, actuals: list[Actual],
              recoveries: list[dict], today: date, weeks_back: int = 8, weeks_ahead: int = 2,
              rules: RuleSet | None = None) -> dict[str, Any]:
    rules = rules or load_rules()
    monday = today - timedelta(days=today.weekday())
    start = monday - timedelta(weeks=weeks_back - 1)
    end = monday + timedelta(weeks=weeks_ahead, days=6)
    adjustments = checkins.adjustments(start, end)
    rec_by_day = {date.fromisoformat(r["date"]): r for r in recoveries}

    weeks, scored = [], {}
    for w in (plan.weeks if plan else ()):
        if not start <= w.start <= end:
            continue
        ws = score_week(w, actuals, as_of=today, adjustments=adjustments, rules=rules) if w.sessions else None
        if ws:
            for s in ws.sessions:
                scored[(s.day, s.kind)] = s
        run_km = sum(a.km for a in actuals if a.kind == "run" and 0 <= (a.day - w.start).days <= 6)
        weeks.append({"start": w.start.isoformat(), "type": w.type, "planned_km": w.km,
                      "actual_km": round(run_km, 1) if w.start <= today else None,
                      "adherence": ws.adherence if ws else None,
                      "execution": ws.execution if ws else None,
                      "football": sum(a.kind == "football" for a in actuals
                                      if 0 <= (a.day - w.start).days <= 6)})

    checkin_by_day = {c.day: c for c in checkins.between(start, end)}
    days = []
    d = start
    while d <= end:
        planned = plan.sessions_on(d) if plan else ()
        rec = rec_by_day.get(d)
        c = checkin_by_day.get(d)
        days.append({
            "date": d.isoformat(),
            "planned": [_session(x, scored.get((x.day, x.kind))) for x in planned],
            "done": [{"kind": a.kind, "minutes": a.minutes, "km": a.km, "strain": a.strain}
                     for a in actuals if a.day == d],
            "checkin": {"decision": c.decision, "reason": c.reason,
                        "adjusted_target": c.adjusted_target} if c else None,
            "recovery": rec["recovery"] if rec else None,
            "hrv": rec["hrv"] if rec else None,
        })
        d += timedelta(days=1)

    return {
        "today": today.isoformat(),
        "goal": {"kind": plan.goal, "race_date": plan.race_date.isoformat(),
                 "days_to_race": (plan.race_date - today).days} if plan else None,
        "days": days,
        "weeks": weeks,
        "activity_cost": activity_cost(actuals, recoveries, plan),
    }


def add_pace_bands(out: dict[str, Any], bands_for: Callable[[date], dict[str, str]]) -> dict[str, Any]:
    """Give each planned session with a pace intent its band in m:ss/km, or None without one.
    bands_for is called once per week: the band only changes when the planned VDOT line steps up."""
    weekly: dict[date, dict[str, str]] = {}
    for d in out["days"]:
        day = date.fromisoformat(d["date"])
        monday = day - timedelta(days=day.weekday())
        if monday not in weekly:
            weekly[monday] = bands_for(day)
        for s in d["planned"]:
            s["pace_band"] = weekly[monday].get(s["pace"]) if s["pace"] else None
    return out


def activity_cost(actuals: list[Actual], recoveries: list[dict], plan: Plan | None = None) -> dict[str, Any]:
    """For each kind of day, the next morning's HRV against the personal median, and recovery.

    A day is labelled by its heaviest activity (Whoop strain, else minutes). Runs are
    split by what the plan asked for that day (easy, quality, long) when there is a plan.
    """
    rec = {date.fromisoformat(r["date"]): r for r in recoveries if r.get("hrv") is not None}
    if not rec:
        return {"baseline_hrv": None, "rows": [], "min_samples": MIN_SAMPLES}
    baseline = median(r["hrv"] for r in rec.values())

    by_day: dict[date, list[Actual]] = {}
    for a in actuals:
        by_day.setdefault(a.day, []).append(a)

    groups: dict[str, list[dict]] = {}
    first, last = min(rec), max(rec)
    d = first - timedelta(days=1)
    while d < last:
        nxt = rec.get(d + timedelta(days=1))
        if nxt:
            label = _label(d, by_day.get(d, []), plan)
            groups.setdefault(label, []).append(nxt)
        d += timedelta(days=1)

    rows = []
    for label, mornings in groups.items():
        rows.append({
            "kind": label,
            "n": len(mornings),
            "hrv_change_pct": round(100 * (mean(m["hrv"] for m in mornings) - baseline) / baseline, 1),
            "next_recovery": round(mean(m["recovery"] for m in mornings), 1),
            "enough": len(mornings) >= MIN_SAMPLES,
        })
    rows.sort(key=lambda r: r["hrv_change_pct"])
    return {"baseline_hrv": round(baseline, 1), "rows": rows, "min_samples": MIN_SAMPLES}


def _label(d: date, acts: list[Actual], plan: Plan | None) -> str:
    if not acts:
        return "rest"
    top = max(acts, key=lambda a: (a.strain or 0, a.minutes))
    if top.kind == "run" and plan:
        planned = [s for s in plan.sessions_on(d) if s.is_run]
        if planned:
            return f"run: {planned[0].kind}"
    return top.kind


def _session(x, score) -> dict[str, Any]:
    out = {"kind": x.kind, "target": x.target, "unit": x.unit, "zone_max": x.zone_max, "note": x.note,
           "pace": x.pace, "structure": x.structure}
    if score:
        s = asdict(score)
        out["score"] = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in s.items()
                        if k in ("status", "planned", "actual", "actual_day", "adherence", "execution", "adjusted")}
    return out
