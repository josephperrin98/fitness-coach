"""The service layer: every entry point (MCP server, CLI, evals) goes through Coach.

Routes stay thin. They parse input, call one method here, and format the answer.
confirm() lives here too, but only the CLI calls it: the MCP server never exposes
it, so an agent has no way to reach it (D5, D20).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from .checkins import CheckIn, CheckInStore
from .checkpoints import Checkpoint, CheckpointStore
from .fitness import RACE_METRES, pace_bands, pace_vdot, vdot, vdot_line
from .gates import check_caution_gate
from .plan import Plan, plan_from_dict
from .rules import RuleSet, load_rules
from .score import score_week
from .sources import actuals_from_strava, actuals_from_whoop, merge
from .store import PlanStore
from .views import add_pace_bands, dashboard

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "coach.db"


def default_db() -> str:
    path = Path(os.environ.get("COACH_DB", DEFAULT_DB))
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


class Coach:
    def __init__(self, db_path: str | None = None, rules: RuleSet | None = None) -> None:
        path = db_path or default_db()
        self.rules = rules or load_rules()
        self.plans = PlanStore(path, self.rules)
        self.checkins = CheckInStore(path)
        self.checkpoints = CheckpointStore(path)

    # -- reads ------------------------------------------------------------------
    def plan(self) -> Plan | None:
        return self.plans.current()

    def today(self, day: date) -> dict[str, Any]:
        plan = self.plan()
        week = plan.week_of(day) if plan else None
        latest = self.checkins.latest(day)
        return {
            "date": day.isoformat(),
            "weekday": day.strftime("%A"),
            "has_plan": plan is not None,
            "week": {"start": week.start.isoformat(), "type": week.type, "km": week.km,
                     "runs": week.runs, "quality": week.quality} if week else None,
            "sessions_today": [_session(s) for s in (plan.sessions_on(day) if plan else ())],
            "rest_of_week": [_session(s) for s in (week.sessions if week else ()) if s.day > day],
            "days_to_race": (plan.race_date - day).days if plan else None,
            "checkin_today": asdict(latest) if latest else None,
            "gate": {k: v for k, v in self.rules.gates["caution_area"].items() if k != "provenance"},
            "paces": self.paces(day),
        }

    def paces(self, day: date) -> dict[str, Any]:
        """Pace bands for the week of `day` (D29, D30)."""
        cp = self.checkpoints.latest(day)
        if cp is None:
            return {"error": "no checkpoint recorded yet: record a confirmed test result first"}
        plan, prog = self.plan(), self.rules.paces["progression"]
        race_m = RACE_METRES[plan.goal] if plan else None
        line = cp.vdot
        if plan and plan.target_time:
            target_day = plan.race_date - timedelta(days=prog["target_lead_days"])
            monday = day - timedelta(days=day.weekday())
            line = vdot_line(plan.weeks, cp.day, cp.vdot, target_day,
                             vdot(race_m, plan.target_time)).get(monday, cp.vdot)
        used = pace_vdot(line, cp.vdot, prog["cap_above_checkpoint"])
        return {
            "day": day.isoformat(),
            "checkpoint": {"day": cp.day.isoformat(), "kind": cp.kind, "vdot": round(cp.vdot, 1)},
            "line_vdot": round(line, 1),
            "vdot_used": round(used, 1),
            "capped": used < line,
            "paces": pace_bands(used, self.rules.paces["intensity"], race_m),
        }

    def gate(self, score: int, effort: str = "run") -> dict[str, str]:
        return asdict(check_caution_gate(score, effort, self.rules))

    def week_score(self, day: date, strava: Any, whoop_workouts: Any) -> dict[str, Any]:
        plan = self.plan()
        week = plan.week_of(day) if plan else None
        if week is None or not week.sessions:
            return {"error": f"no planned sessions for the week of {day}"}
        acts = merge(actuals_from_strava(_rows(strava, "activities")), actuals_from_whoop(_rows(whoop_workouts)))
        ws = score_week(week, acts, as_of=day, adjustments=self.checkins.adjustments(), rules=self.rules)
        return json.loads(json.dumps(asdict(ws), default=str))

    def dashboard(self, today: date, strava: Any, whoop_workouts: Any, whoop_recovery: Any,
                  weeks_back: int = 8, weeks_ahead: int = 2) -> dict[str, Any]:
        acts = merge(actuals_from_strava(_rows(strava, "activities")), actuals_from_whoop(_rows(whoop_workouts)))
        out = dashboard(self.plan(), self.checkins, acts, _rows(whoop_recovery), today,
                        weeks_back, weeks_ahead, self.rules)
        # Bands depend on checkpoints, which views.dashboard does not see.
        return add_pace_bands(out, lambda day: self.paces(day).get("paces", {}))

    # -- writes the agent may make ------------------------------------------------
    def record_check_in(self, c: CheckIn) -> dict[str, Any]:
        return asdict(self.checkins.record(c, self.plan()))

    def record_checkpoint(self, c: Checkpoint) -> dict[str, Any]:
        """Only after the athlete confirmed the numbers in chat (D31)."""
        self.checkpoints.record(c)
        return {"day": c.day.isoformat(), "kind": c.kind, "vdot": round(c.vdot, 1)}

    def propose(self, plan_data: dict[str, Any] | str, rationale: str, author: str = "agent") -> dict[str, Any]:
        data = yaml.safe_load(plan_data) if isinstance(plan_data, str) else plan_data
        p = self.plans.propose(plan_from_dict(data), author=author, rationale=rationale)
        return {"version": p.version, "status": p.status,
                "findings": [str(v) for v in p.violations],
                "next_step": ("broke a hard rule: cannot be confirmed" if p.status == "rejected" else
                              "pending: the user confirms it from the command line")}

    # -- human only (CLI) -------------------------------------------------------------
    def confirm(self, version: int, acknowledged: set[str]) -> None:
        self.plans.confirm(version, acknowledged)

    def pending(self) -> list[dict]:
        return [h for h in self.plans.history() if h["status"] == "pending"]


def week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def _session(s) -> dict[str, Any]:
    return {"day": s.day.isoformat(), "kind": s.kind, "target": s.target, "unit": s.unit,
            "zone_max": s.zone_max, "note": s.note, "pace": s.pace, "structure": s.structure}


def _rows(value: Any, key: str | None = None) -> list[dict]:
    """Accept a connector's answer as a JSON string, a list, or a dict wrapping the list."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict):
        value = value.get(key or "", value.get("result", []))
        if isinstance(value, str):
            value = json.loads(value)
    return list(value)
