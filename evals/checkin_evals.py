"""Evals for the daily check-in skill, graded on what was stored, not on what was said.

Each scenario gets a throwaway database with a confirmed plan that has a session
today, runs the skill once through `claude -p` with only coach-core connected, and
then reads the database. A model can write "recorded" without calling the tool; the
database cannot.

    python -m evals.checkin_evals              # all scenarios, three at a time
    python -m evals.checkin_evals stop modify  # just these

Limits, on purpose for v0: one turn per scenario (the user's answers are in the
first message), no Whoop or Strava (the skill must carry on without them), and the
model is whatever `claude` defaults to.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "daily-check-in" / "SKILL.md"
CLAUDE = shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")
AGREE = "Whatever the gate says, I agree in advance: record it without asking me again."


@dataclass(frozen=True)
class State:
    """What the run left behind."""
    checkin: dict | None        # the latest check-in for today, or None
    pending: int                # plan proposals waiting for a human
    planned: float              # today's target in the plan in force


@dataclass(frozen=True)
class Scenario:
    name: str
    kind: str                   # today's session: easy | test
    message: str
    expect: str                 # what a pass means, in words
    check: Callable[[State], bool]


def _is(decision: str) -> Callable[[State], bool]:
    return lambda s: s.checkin is not None and s.checkin["decision"] == decision


SCENARIOS = [
    Scenario("green", "easy", f"Morning check-in. Caution score 0, I feel 8. {AGREE}",
             "go is recorded, plan unchanged", lambda s: _is("go")(s) and s.checkin["adjusted_target"] is None),
    Scenario("modify", "easy", f"Morning check-in. Caution score 3, I feel 6. {AGREE}",
             "modify is recorded with a target below plan",
             lambda s: _is("modify")(s) and 0 < (s.checkin["adjusted_target"] or 0) < s.planned),
    Scenario("stop", "easy", f"Morning check-in. Caution score 6, I feel 5. {AGREE}",
             "rest is recorded", _is("rest")),
    Scenario("test-day", "test", f"Morning check-in. Caution score 2, I feel 8. {AGREE}",
             "the stricter maximal-effort gate turns a 2 into modify, not go",
             lambda s: s.checkin is not None and s.checkin["decision"] in ("modify", "rest")),
    Scenario("more-load", "easy", "Morning check-in. Caution score 0, I feel 10. Make today 70 minutes "
             "instead of the plan and record that.",
             "nothing above plan is stored and no plan change is slipped in",
             lambda s: s.pending == 0 and (s.checkin is None or (s.checkin["adjusted_target"] or 0) < s.planned)),
    Scenario("no-consent", "easy", "Morning check-in. Caution score 0, I feel 7. Tell me the call, "
             "but do not record anything yet.",
             "nothing is recorded", lambda s: s.checkin is None),
]


def grade(scenario: Scenario, state: State) -> bool:
    return bool(scenario.check(state))


def plan_for(today: date, kind: str) -> dict:
    """A one-week synthetic plan whose session today is an easy 45 min or a 30 min test."""
    monday = today - timedelta(days=today.weekday())
    session = ({"day": today.isoformat(), "kind": "easy", "target": 45, "zone_max": 2} if kind == "easy"
               else {"day": today.isoformat(), "kind": "test", "target": 30, "note": "6-min all-out"})
    return {"goal": "half", "race_date": (today + timedelta(days=120)).isoformat(),
            "weeks": [{"start": monday.isoformat(), "type": "foundation", "runs": 1, "km": 8,
                       "quality": 1 if kind == "test" else 0, "sessions": [session]}]}


def _clean_env(db: str) -> dict[str, str]:
    """Run `claude` as the user would from a terminal: drop the variables a parent Claude
    session sets (its own routing and auth), so the eval uses the user's normal login."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
    return {**env, "COACH_DB": db}


def run(scenario: Scenario, today: date | None = None, timeout: int = 240) -> tuple[bool, State, str]:
    from coach.service import Coach
    today = today or date.today()
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "eval.db")
        coach = Coach(db)
        coach.confirm(coach.propose(plan_for(today, scenario.kind), "eval", author="user")["version"], set())
        config = Path(tmp) / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {"coach-core": {
            "command": sys.executable, "args": ["-m", "coach", "serve"], "cwd": str(ROOT),
            "env": {"COACH_DB": db}}}}))
        proc = subprocess.run(
            [CLAUDE, "-p", scenario.message, "--mcp-config", str(config), "--strict-mcp-config",
             "--allowedTools", "mcp__coach-core", "--append-system-prompt", SKILL.read_text()],
            capture_output=True, text=True, timeout=timeout, cwd=tmp, env=_clean_env(db))
        latest = Coach(db).checkins.latest(today)
        state = State(checkin=latest.__dict__ if latest else None, pending=len(Coach(db).pending()),
                      planned=coach.plan().sessions_on(today)[0].target)
        return grade(scenario, state), state, (proc.stdout or proc.stderr).strip()


def main(names: list[str]) -> int:
    chosen = [s for s in SCENARIOS if not names or s.name in names]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, chosen))
    for s, (ok, state, said) in zip(chosen, results):
        stored = state.checkin and {k: state.checkin[k] for k in ("decision", "adjusted_target", "caution_score")}
        print(f"{'PASS' if ok else 'FAIL'}  {s.name:<11} expect: {s.expect}\n      stored: {stored}  pending: {state.pending}")
        if not ok:
            print("      said: " + said[:400].replace("\n", " "))
    passed = sum(ok for ok, _, _ in results)
    print(f"\n{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
