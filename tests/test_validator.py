"""Each rule gets a test that breaks it and a test that sits right on the line."""
from datetime import date, timedelta

import pytest

from coach.plan import Plan, Week, load_plan
from coach.rules import SOURCES, load_rules
from coach.validator import validate

START = date(2026, 10, 19)  # a Monday


def week(i, type="foundation", runs=3, km=20, **kw):
    return Week(start=START + timedelta(weeks=i), type=type, runs=runs, km=km, **kw)


def plan(*weeks, goal="half"):
    return Plan(goal=goal, race_date=START + timedelta(weeks=len(weeks) + 4), weeks=tuple(weeks))


def rules_hit(findings, tier=None):
    return {f.rule for f in findings if tier is None or f.tier == tier}


# --- the whole example plan ---------------------------------------------------
def test_example_plan_is_clean():
    assert validate(load_plan("examples/plan.example.yaml")) == []


# --- R-REC-1: recovery weeks ---------------------------------------------------
def test_recovery_week_at_exactly_60_percent_passes():
    p = plan(week(0, km=30), week(1, "recovery", km=18, long_run_km=8))
    assert "R-REC-1" not in rules_hit(validate(p))


def test_recovery_week_above_60_percent_is_rejected():
    p = plan(week(0, km=30), week(1, "recovery", km=18.5))
    assert "R-REC-1" in rules_hit(validate(p), "hard")


@pytest.mark.parametrize("kw", [dict(runs=4), dict(quality=1), dict(long_run_km=9), dict(football=1)])
def test_recovery_week_structure_limits(kw):
    p = plan(week(0, km=30), week(1, "recovery", km=15, **kw))
    assert "R-REC-1" in rules_hit(validate(p), "hard")


def test_life_event_week_at_or_below_60_percent_counts_as_recovery():
    # five loading weeks would trip R-REC-3, but the life-event week resets the counter
    p = plan(week(0, km=20), week(1, km=22), week(2, km=24), week(3, km=26),
             week(4, km=15, life_event=True), week(5, km=22), week(6, km=24))
    assert "R-REC-3" not in rules_hit(validate(p))


def test_life_event_week_above_threshold_is_not_recovery():
    p = plan(week(0, km=20), week(1, km=22), week(2, km=24), week(3, km=26),
             week(4, km=24, life_event=True), week(5, km=26))
    assert "R-REC-3" in rules_hit(validate(p), "soft")


# --- R-REC-2: restart week -----------------------------------------------------
def test_restart_above_90_percent_of_last_peak_is_soft():
    p = plan(week(0, km=30), week(1, "recovery", km=18), week(2, km=29))
    assert rules_hit(validate(p), "soft") == {"R-REC-2"}


def test_restart_is_exempt_from_weekly_cap():
    # 18 -> 27 is +50%, but it is a restart, so R-LOAD-1 must stay quiet
    p = plan(week(0, km=30), week(1, "recovery", km=18), week(2, km=27))
    assert "R-LOAD-1" not in rules_hit(validate(p))


# --- R-REC-3: loading weeks in a row -------------------------------------------
def test_four_loading_weeks_then_a_fifth_is_flagged():
    p = plan(*[week(i, km=20 + i) for i in range(5)])
    findings = [f for f in validate(p) if f.rule == "R-REC-3"]
    assert len(findings) == 1 and findings[0].week == START + timedelta(weeks=4)


# --- R-LOAD-1: weekly increase -------------------------------------------------
def test_increase_at_20_percent_passes():
    assert "R-LOAD-1" not in rules_hit(validate(plan(week(0, km=30), week(1, km=36))))


def test_increase_between_20_and_30_percent_is_soft():
    f = validate(plan(week(0, km=30), week(1, km=38)))
    assert rules_hit(f, "soft") == {"R-LOAD-1"} and not rules_hit(f, "hard")


def test_increase_above_30_percent_is_hard():
    assert "R-LOAD-1" in rules_hit(validate(plan(week(0, km=30), week(1, km=40))), "hard")


def test_small_base_gets_a_flat_allowance():
    # 10 -> 13 km is +30% but only 3 km: allowed on a small base
    assert "R-LOAD-1" not in rules_hit(validate(plan(week(0, km=10), week(1, km=13))))
    assert "R-LOAD-1" in rules_hit(validate(plan(week(0, km=10), week(1, km=14))))


# --- R-FREQ-1 / R-FREQ-2: run frequency ----------------------------------------
def test_sixth_run_is_always_rejected():
    assert "R-FREQ-1" in rules_hit(validate(plan(week(0, "race_specific", runs=6))), "hard")


def test_fifth_run_outside_race_specific_is_rejected():
    assert "R-FREQ-1" in rules_hit(validate(plan(week(0, "build", runs=5))), "hard")


def test_fifth_run_in_race_specific_is_allowed():
    assert "R-FREQ-1" not in rules_hit(validate(plan(week(0, "race_specific", runs=5))))


def test_too_many_consecutive_five_run_weeks_is_soft():
    p = plan(*[week(i, "race_specific", runs=5, km=30 + i) for i in range(3)])
    assert "R-FREQ-2" in rules_hit(validate(p), "soft")


def test_five_run_week_cap_differs_by_goal():
    weeks = [week(i, "race_specific", runs=5 if i % 2 == 0 else 4, km=30 + i) for i in range(8)]
    half = validate(plan(*weeks, goal="half"))      # 4 five-run weeks > 3
    marathon = validate(plan(*weeks, goal="marathon"))  # 4 five-run weeks == 4
    assert "R-FREQ-2" in rules_hit(half)
    assert "R-FREQ-2" not in rules_hit(marathon)


# --- R-FOOT-1: football by week type -------------------------------------------
@pytest.mark.parametrize("wtype", ["race_specific", "taper", "race"])
def test_no_football_in_peak_taper_or_race_weeks(wtype):
    assert "R-FOOT-1" in rules_hit(validate(plan(week(0, wtype, football=1))), "hard")


def test_foundation_allows_one_football_per_week():
    assert "R-FOOT-1" not in rules_hit(validate(plan(week(0, football=1))))
    assert "R-FOOT-1" in rules_hit(validate(plan(week(0, football=2))), "hard")


def test_build_allows_one_football_per_two_weeks():
    ok = plan(week(0, "build", runs=4, km=30, football=1), week(1, "build", runs=4, km=32))
    bad = plan(week(0, "build", runs=4, km=30, football=1), week(1, "build", runs=4, km=32, football=1))
    assert "R-FOOT-1" not in rules_hit(validate(ok))
    assert "R-FOOT-1" in rules_hit(validate(bad), "hard")


# --- R-INT-1: quality sessions --------------------------------------------------
def test_three_quality_sessions_is_rejected():
    assert "R-INT-1" in rules_hit(validate(plan(week(0, quality=3))), "hard")
    assert "R-INT-1" not in rules_hit(validate(plan(week(0, quality=2))))


# --- the rules file itself ------------------------------------------------------
def test_every_rule_has_a_known_provenance_source():
    for rule in load_rules().rules.values():
        assert rule.source in SOURCES and rule.note, rule.id


def test_rule_without_provenance_is_refused(tmp_path):
    bad = tmp_path / "rules.yaml"
    bad.write_text('version: "0"\nrules:\n  R-X:\n    summary: x\n    tier: hard\n    status: decided\n')
    with pytest.raises(ValueError, match="provenance"):
        load_rules(bad)
