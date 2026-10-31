"""Sessions inside a week: each planned session is written out, and must agree with the week totals."""
from datetime import date, timedelta

import pytest

from coach.plan import Session, Week, plan_from_dict, plan_to_dict

MON = date(2026, 10, 19)


def s(offset, kind="easy", target=45, unit="min", **kw):
    return Session(day=MON + timedelta(days=offset), kind=kind, target=target, unit=unit, **kw)


def test_week_with_matching_sessions_is_valid():
    w = Week(start=MON, type="foundation", runs=3, km=20, quality=1, football=1,
             sessions=(s(0), s(2, "quality", 40), s(4, "football", 90), s(6, "long", 10, "km")))
    assert len(w.sessions) == 4
    assert [x.kind for x in w.run_sessions] == ["easy", "quality", "long"]


def test_session_outside_its_week_is_refused():
    with pytest.raises(ValueError, match="outside"):
        Week(start=MON, type="foundation", runs=1, km=5, sessions=(s(7),))


def test_run_count_must_match_week_total():
    with pytest.raises(ValueError, match="runs"):
        Week(start=MON, type="foundation", runs=3, km=20, sessions=(s(0), s(2)))


def test_quality_count_includes_tests():
    w = Week(start=MON, type="foundation", runs=2, km=12, quality=1,
             sessions=(s(0), s(2, "test", 30)))
    assert w.quality == 1
    with pytest.raises(ValueError, match="quality"):
        Week(start=MON, type="foundation", runs=2, km=12, quality=0, sessions=(s(0), s(2, "test", 30)))


def test_football_count_must_match():
    with pytest.raises(ValueError, match="football"):
        Week(start=MON, type="foundation", runs=1, km=5, football=0, sessions=(s(0), s(3, "football", 90)))


def test_unknown_kind_and_unit_are_refused():
    with pytest.raises(ValueError, match="kind"):
        s(0, kind="swim")
    with pytest.raises(ValueError, match="unit"):
        s(0, unit="miles")


def test_week_without_sessions_still_works():
    w = Week(start=MON, type="foundation", runs=3, km=20)
    assert w.sessions == ()


def test_sessions_round_trip_through_dict():
    data = {
        "goal": "half", "race_date": "2027-03-14",
        "weeks": [{"start": "2026-10-19", "type": "foundation", "runs": 1, "km": 8,
                   "sessions": [{"day": "2026-10-19", "kind": "easy", "target": 45, "unit": "min",
                                 "zone_max": 2, "note": "steady"}]}],
    }
    plan = plan_from_dict(data)
    assert plan.weeks[0].sessions[0].zone_max == 2
    again = plan_from_dict(plan_to_dict(plan))
    assert again == plan


def test_plan_finds_session_by_day():
    data = {"goal": "half", "race_date": "2027-03-14",
            "weeks": [{"start": "2026-10-19", "type": "foundation", "runs": 1, "km": 8,
                       "sessions": [{"day": "2026-10-21", "kind": "easy", "target": 40}]}]}
    plan = plan_from_dict(data)
    assert [x.target for x in plan.sessions_on(date(2026, 10, 21))] == [40]
    assert plan.sessions_on(date(2026, 10, 22)) == ()
    assert plan.week_of(date(2026, 10, 25)).start == MON


def test_session_and_plan_carry_pace_intent_round_trip():
    from coach.plan import plan_from_dict, plan_to_dict
    data = {"goal": "half", "race_date": "2027-03-14", "target_time": "1:30:00",
            "weeks": [{"start": "2026-11-02", "type": "foundation", "runs": 1, "km": 8, "quality": 1,
                       "sessions": [{"day": "2026-11-03", "kind": "quality", "target": 50,
                                     "pace": "threshold", "structure": "3 x 10 min"}]}]}
    plan = plan_from_dict(data)
    s = plan.weeks[0].sessions[0]
    assert (plan.target_time, s.pace, s.structure) == (5400, "threshold", "3 x 10 min")
    again = plan_from_dict(plan_to_dict(plan))
    assert again == plan


def test_unknown_pace_kind_is_refused():
    import pytest
    from datetime import date
    from coach.plan import Session
    with pytest.raises(ValueError, match="pace"):
        Session(day=date(2026, 11, 3), kind="easy", pace="sprinty")


def _plan_with_target(target):
    return {"goal": "half", "race_date": "2027-03-14", "target_time": target,
            "weeks": [{"start": "2026-11-02", "type": "foundation", "runs": 1, "km": 8}]}


def test_unquoted_yaml_target_time_is_refused():
    import yaml
    # YAML 1.1 reads an unquoted 1:45 as the base-60 integer 105 (seconds).
    data = yaml.safe_load("goal: half\nrace_date: 2027-03-14\ntarget_time: 1:45\n"
                          "weeks:\n  - {start: 2026-11-02, type: foundation, runs: 1, km: 8}\n")
    with pytest.raises(ValueError, match="target_time"):
        plan_from_dict(data)


@pytest.mark.parametrize("bad", ["0:00:00", "1:75:00", "1:30:75", "-1:30:00", "a:b", "1:2:3:4"])
def test_implausible_or_malformed_target_time_is_refused(bad):
    with pytest.raises(ValueError, match="target_time"):
        plan_from_dict(_plan_with_target(bad))
