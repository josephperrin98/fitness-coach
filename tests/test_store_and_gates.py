from datetime import date, timedelta

import pytest

from coach.gates import check_caution_gate
from coach.plan import Plan, Week, load_plan
from coach.store import ConfirmationError, PlanStore

START = date(2026, 10, 19)


def wk(i, km, type="foundation", runs=3, **kw):
    return Week(start=START + timedelta(weeks=i), type=type, runs=runs, km=km, **kw)


def plan(*weeks):
    return Plan(goal="half", race_date=START + timedelta(weeks=10), weeks=tuple(weeks))


GOOD = plan(wk(0, 20), wk(1, 22))
SOFT = plan(wk(0, 30), wk(1, 38))           # +27%: soft R-LOAD-1
HARD = plan(wk(0, 30), wk(1, 45))           # +50%: hard R-LOAD-1


# --- propose / confirm lifecycle -------------------------------------------------
def test_clean_proposal_is_pending_until_confirmed():
    s = PlanStore()
    p = s.propose(GOOD, rationale="first plan")
    assert p.status == "pending" and s.current() is None
    s.confirm(p.version)
    assert s.current() == GOOD


def test_hard_violation_is_stored_for_audit_but_never_confirmable():
    s = PlanStore()
    p = s.propose(HARD)
    assert p.status == "rejected" and p.hard
    with pytest.raises(ConfirmationError, match="hard rule"):
        s.confirm(p.version, {"R-LOAD-1"})
    assert s.current() is None
    assert s.history()[0]["status"] == "rejected"


def test_soft_violation_requires_explicit_acknowledgement():
    s = PlanStore()
    p = s.propose(SOFT)
    assert p.status == "pending" and [v.rule for v in p.soft] == ["R-LOAD-1"]
    with pytest.raises(ConfirmationError, match="R-LOAD-1"):
        s.confirm(p.version)
    s.confirm(p.version, {"R-LOAD-1"})
    assert s.current() == SOFT


def test_confirming_a_new_plan_supersedes_the_old_one():
    s = PlanStore()
    first = s.propose(GOOD)
    s.confirm(first.version)
    second = s.propose(plan(wk(0, 20), wk(1, 23)))
    s.confirm(second.version)
    statuses = {h["version"]: h["status"] for h in s.history()}
    assert statuses == {first.version: "superseded", second.version: "confirmed"}


def test_withdrawn_proposal_cannot_be_confirmed():
    s = PlanStore()
    p = s.propose(GOOD)
    s.withdraw(p.version)
    with pytest.raises(ConfirmationError):
        s.confirm(p.version)


def test_example_plan_round_trips_through_the_store():
    example = load_plan("examples/plan.example.yaml")
    s = PlanStore()
    s.confirm(s.propose(example, author="test").version)
    assert s.current() == example


def test_store_survives_reopening(tmp_path):
    path = str(tmp_path / "coach.db")
    s = PlanStore(path)
    s.confirm(s.propose(GOOD).version)
    assert PlanStore(path).current() == GOOD


# --- day-of caution gate ---------------------------------------------------------
@pytest.mark.parametrize("score,effort,expected", [
    (0, "run", "go"), (2, "run", "go"),
    (3, "run", "modify"), (4, "run", "modify"),
    (5, "run", "stop"), (9, "run", "stop"),
    (1, "maximal", "go"),
    (2, "maximal", "modify"),     # fine for easy running, not for an all-out test
    (5, "maximal", "stop"),
])
def test_caution_gate_ladder(score, effort, expected):
    assert check_caution_gate(score, effort).decision == expected


def test_caution_gate_rejects_out_of_range_scores():
    with pytest.raises(ValueError):
        check_caution_gate(11)
