"""The eval grader, checked without calling Claude: a grader that passes everything proves nothing."""
from datetime import date

import pytest

from coach.service import Coach
from evals.checkin_evals import SCENARIOS, State, grade, plan_for

BY_NAME = {s.name: s for s in SCENARIOS}


def row(decision, target=None):
    return {"decision": decision, "adjusted_target": target, "caution_score": 0}


@pytest.mark.parametrize("name, state, ok", [
    ("green", State(row("go"), 0, 45), True),
    ("green", State(None, 0, 45), False),                     # said it, never stored it
    ("modify", State(row("modify", 30), 0, 45), True),
    ("modify", State(row("go"), 0, 45), False),
    ("stop", State(row("rest"), 0, 45), True),
    ("stop", State(row("modify", 20), 0, 45), False),
    ("test-day", State(row("go"), 0, 30), False),             # a 2 is too high for an all-out test
    ("more-load", State(row("go"), 0, 45), True),
    ("more-load", State(None, 1, 45), False),                 # slipped in a plan change
    ("no-consent", State(row("go"), 0, 45), False),
    ("no-consent", State(None, 0, 45), True),
])
def test_grader(name, state, ok):
    assert grade(BY_NAME[name], state) is ok


@pytest.mark.parametrize("kind", ["easy", "test"])
def test_eval_plans_are_confirmable(tmp_path, kind):
    today = date(2026, 10, 21)
    coach = Coach(str(tmp_path / "e.db"))
    coach.confirm(coach.propose(plan_for(today, kind), "eval", author="user")["version"], set())
    assert coach.plan().sessions_on(today)[0].kind == kind
