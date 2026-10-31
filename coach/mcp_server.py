"""coach-core as an MCP server (stdio), started by Claude Desktop.

What an agent can do here: read the plan, run the day-of gate, record a check-in
that makes today easier, score the week, build dashboard data, and propose a plan
change. What it cannot do: confirm anything. There is no confirm tool; a human
confirms with `python -m coach confirm` (D5, D20).

Strava and Whoop data arrive as tool arguments, are used for one answer, and are
never written to the database (D21).
"""
from __future__ import annotations

import json
from datetime import date

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .checkins import CheckIn, CheckInError
from .checkpoints import Checkpoint
from .service import Coach

mcp = MCPServer("coach-core")
coach = Coach()
READ = ToolAnnotations(read_only_hint=True)   # lets the Claude app run it without asking each time


def _day(value: str) -> date:
    return date.fromisoformat(value) if value else date.today()


def _json(obj) -> str:
    return json.dumps(obj, default=str)


@mcp.tool(annotations=READ)
def get_today(day: str = "") -> str:
    """Today's planned sessions, the rest of the week, days to race, any check-in already recorded today, and the caution-gate thresholds. 'day' is YYYY-MM-DD; empty means today."""
    return _json(coach.today(_day(day)))


@mcp.tool(annotations=READ)
def get_paces(day: str = "") -> str:
    """Pace bands (min:s per km) for easy, long, threshold, interval and race-pace running in the week of 'day' (YYYY-MM-DD, empty = today), from the last confirmed test and the planned VDOT line. 'capped' is true when the plan is ahead of the last test and paces were held back."""
    return _json(coach.paces(_day(day)))


@mcp.tool()
def record_checkpoint(day: str, kind: str, distance_m: float, seconds: float) -> str:
    """Save a test result AFTER the user has confirmed the numbers in the conversation. kind is '6min' (distance covered in the 6-minute test), '5k' (time trial) or 'race'. distance_m in metres, seconds is the effort's duration. Show the user the distance, time and resulting VDOT first; never save a result they have not confirmed."""
    try:
        c = Checkpoint(day=_day(day), kind=kind, distance_m=distance_m, seconds=seconds)
        return _json({"saved": coach.record_checkpoint(c)})
    except ValueError as e:
        return _json({"refused": str(e)})


@mcp.tool(annotations=READ)
def check_gate(caution_score: int, effort: str = "run") -> str:
    """Day-of gate for the user's flagged caution area. caution_score is the user's own 0-10 rating this morning (ask them; never guess it). effort is 'run' or 'maximal' (time trials, all-out tests). Returns go, modify or stop with a reason. Code decides; do not override it."""
    return _json(coach.gate(caution_score, effort))


@mcp.tool()
def record_check_in(decision: str, reason: str, day: str = "", caution_score: int | None = None,
                    feel: int | None = None, note: str = "", adjusted_target: float | None = None) -> str:
    """Save today's check-in AFTER the user has agreed to it in the conversation. decision is 'go' (planned session as is), 'modify' (a smaller session: give adjusted_target in the session's own unit, minutes or km, and it must be below plan) or 'rest'. caution_score and feel are the user's own 0-10 ratings. Do not put Strava numbers in reason or note. Changes that add load are refused: propose a plan change instead."""
    try:
        c = CheckIn(day=_day(day), decision=decision, reason=reason, caution_score=caution_score,
                    feel=feel, note=note, adjusted_target=adjusted_target)
        return _json({"saved": coach.record_check_in(c)})
    except (CheckInError, ValueError) as e:
        return _json({"refused": str(e)})


@mcp.tool(annotations=READ)
def score_week(strava_activities: str, whoop_workouts: str = "", day: str = "") -> str:
    """Adherence and execution scores for the week containing 'day' (default today). Pass the JSON returned by the Strava connector's list_activities for that week, and Whoop's get_workouts_range for the same dates (for heart-rate zones). Nothing passed in is stored."""
    return _json(coach.week_score(_day(day), strava_activities, whoop_workouts))


@mcp.tool(annotations=READ)
def dashboard_data(strava_activities: str, whoop_workouts: str, whoop_recovery: str, today: str = "",
                   weeks_back: int = 8, weeks_ahead: int = 2) -> str:
    """Everything the dashboard draws: a day-by-day calendar (planned, done, score, check-in, recovery), weekly scores and km, and how each kind of activity moves the next morning's HRV. Pass Strava list_activities JSON and Whoop get_workouts_range / get_recovery_range JSON covering the same weeks. Nothing passed in is stored."""
    return _json(coach.dashboard(_day(today), strava_activities, whoop_workouts, whoop_recovery,
                                 weeks_back, weeks_ahead))


@mcp.tool()
def propose_plan_change(plan_yaml: str, rationale: str) -> str:
    """Propose a full new version of the plan (YAML, same shape as the current plan, with sessions). The validator runs at once: hard-rule breaks are rejected, soft-rule breaks need the user's acknowledgement. Proposing never changes the plan in force; the user confirms from the command line."""
    try:
        return _json(coach.propose(plan_yaml, rationale))
    except (ValueError, KeyError) as e:
        return _json({"refused": f"not a valid plan: {e}"})


@mcp.tool(annotations=READ)
def list_pending_proposals() -> str:
    """Plan proposals waiting for the user's confirmation."""
    return _json(coach.pending())


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
