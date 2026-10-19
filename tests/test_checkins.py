"""Daily check-ins (D18, D20): today only, and the agent can only make today easier."""
from datetime import date

import pytest

from coach.checkins import CheckIn, CheckInError, CheckInStore
from coach.plan import plan_from_dict

PLAN = plan_from_dict({
    "goal": "half", "race_date": "2027-03-14",
    "weeks": [{"start": "2026-10-19", "type": "foundation", "runs": 2, "km": 12, "quality": 1,
               "sessions": [{"day": "2026-10-19", "kind": "easy", "target": 45, "zone_max": 2},
                            {"day": "2026-10-21", "kind": "test", "target": 30}]}],
})
MON, WED = date(2026, 10, 19), date(2026, 10, 21)


@pytest.fixture
def store():
    return CheckInStore(":memory:")


def test_go_is_recorded(store):
    store.record(CheckIn(day=MON, decision="go", reason="recovery 64%", caution_score=1), PLAN)
    assert store.latest(MON).decision == "go"


def test_shorter_session_is_allowed_and_becomes_an_adjustment(store):
    store.record(CheckIn(day=MON, decision="modify", reason="recovery 16%", adjusted_target=30), PLAN)
    adj = store.adjustments()[MON]
    assert adj.target == 30 and adj.unit == "min" and not adj.rest


def test_longer_session_is_refused(store):
    # Adding load is a plan change: it goes through propose/confirm, never a check-in.
    with pytest.raises(CheckInError, match="easier"):
        store.record(CheckIn(day=MON, decision="modify", reason="feel great", adjusted_target=60), PLAN)


def test_modify_needs_a_planned_session(store):
    with pytest.raises(CheckInError, match="no planned"):
        store.record(CheckIn(day=date(2026, 10, 20), decision="modify", reason="x", adjusted_target=20), PLAN)


def test_rest_is_always_allowed(store):
    store.record(CheckIn(day=WED, decision="rest", reason="ankle 5/10", caution_score=5), PLAN)
    assert store.adjustments()[WED].rest


def test_go_cannot_carry_a_new_target(store):
    with pytest.raises(CheckInError, match="go"):
        store.record(CheckIn(day=MON, decision="go", reason="x", adjusted_target=30), PLAN)


def test_unknown_decision_is_refused():
    with pytest.raises(ValueError, match="decision"):
        CheckIn(day=MON, decision="maybe", reason="x")


def test_latest_check_in_of_the_day_wins(store):
    store.record(CheckIn(day=MON, decision="go", reason="first"), PLAN)
    store.record(CheckIn(day=MON, decision="rest", reason="changed my mind"), PLAN)
    assert store.latest(MON).reason == "changed my mind"
    assert len(store.between(MON, MON)) == 1


def test_between_returns_one_record_per_day_in_order(store):
    store.record(CheckIn(day=WED, decision="go", reason="b"), PLAN)
    store.record(CheckIn(day=MON, decision="go", reason="a"), PLAN)
    assert [c.reason for c in store.between(MON, WED)] == ["a", "b"]
