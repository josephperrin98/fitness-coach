"""Adherence and execution scores (D17): falling short costs twice what overshooting does."""
from datetime import date, timedelta

import pytest

from coach.plan import Session, Week
from coach.score import Actual, Adjustment, adherence, score_week

MON = date(2026, 10, 19)


def day(i):
    return MON + timedelta(days=i)


def week(*sessions, runs=None, quality=0, football=0):
    runs = sum(x.is_run for x in sessions) if runs is None else runs
    return Week(start=MON, type="foundation", runs=runs, km=20, quality=quality,
                football=football, sessions=sessions)


def run(i, minutes=0.0, km=0.0, zones=None):
    return Actual(day=day(i), kind="run", minutes=minutes, km=km, zone_minutes=zones)


# --- the formula --------------------------------------------------------------

def test_the_agreed_examples():
    assert adherence(35, 45) == pytest.approx(77.8, abs=0.1)   # short: 100 * r
    assert adherence(58, 45) == pytest.approx(85.6, abs=0.1)   # over: 100 - 50 * (r - 1)
    assert adherence(45, 45) == 100


def test_overshoot_floors_at_zero():
    assert adherence(200, 45) == 0


def test_no_target_means_done_is_enough():
    assert adherence(30, 0) == 100


# --- matching a week ----------------------------------------------------------

def test_short_run_on_the_right_day():
    w = week(Session(day(0), "easy", 45))
    result = score_week(w, [run(0, minutes=35)], as_of=day(6))
    s = result.sessions[0]
    assert s.status == "short" and s.adherence == pytest.approx(77.8, abs=0.1)
    assert result.adherence == pytest.approx(77.8, abs=0.1)


def test_long_run_scored_in_km():
    w = week(Session(day(6), "long", 12, unit="km"))
    s = score_week(w, [run(6, minutes=70, km=13.2)], as_of=day(6)).sessions[0]
    assert s.status == "over" and s.adherence == pytest.approx(95.0)


def test_two_runs_on_one_day_are_added_together():
    w = week(Session(day(0), "easy", 60))
    s = score_week(w, [run(0, minutes=20), run(0, minutes=40)], as_of=day(6)).sessions[0]
    assert s.adherence == 100


def test_missed_session_scores_zero():
    w = week(Session(day(0), "easy", 45), Session(day(2), "easy", 45))
    result = score_week(w, [run(0, minutes=45)], as_of=day(6))
    assert [s.status for s in result.sessions] == ["done", "missed"]
    assert result.adherence == 50


def test_moved_session_loses_ten_points():
    w = week(Session(day(1), "easy", 45))
    s = score_week(w, [run(3, minutes=45)], as_of=day(6)).sessions[0]
    assert s.status == "moved" and s.adherence == 90 and s.actual_day == day(3)


def test_future_sessions_are_upcoming_not_missed():
    w = week(Session(day(0), "easy", 45), Session(day(4), "easy", 45))
    result = score_week(w, [run(0, minutes=45)], as_of=day(2))
    assert [s.status for s in result.sessions] == ["done", "upcoming"]
    assert result.adherence == 100


def test_unplanned_run_is_reported_as_extra():
    w = week(Session(day(0), "easy", 45))
    result = score_week(w, [run(0, minutes=45), run(5, minutes=30)], as_of=day(6))
    assert [a.day for a in result.extra] == [day(5)]


def test_football_scored_as_done_or_not():
    w = week(Session(day(0), "easy", 45), Session(day(3), "football"), football=1)
    result = score_week(w, [run(0, minutes=45),
                            Actual(day=day(3), kind="football", minutes=90)], as_of=day(6))
    assert [s.status for s in result.sessions] == ["done", "done"]


# --- check-in adjustments ----------------------------------------------------

def test_agreed_shorter_session_is_scored_against_the_new_target():
    w = week(Session(day(0), "easy", 45))
    adj = {day(0): Adjustment(target=30, unit="min")}
    s = score_week(w, [run(0, minutes=32)], as_of=day(6), adjustments=adj).sessions[0]
    assert s.planned == 30 and s.adherence > 95 and s.adjusted


def test_agreed_rest_day_is_excused_not_missed():
    w = week(Session(day(0), "easy", 45), Session(day(2), "easy", 45))
    adj = {day(0): Adjustment(target=0, unit="min", rest=True)}
    result = score_week(w, [run(2, minutes=45)], as_of=day(6), adjustments=adj)
    assert [s.status for s in result.sessions] == ["excused", "done"]
    assert result.adherence == 100


# --- execution ---------------------------------------------------------------

def test_execution_is_share_of_minutes_at_or_below_zone_ceiling():
    w = week(Session(day(0), "easy", 45, zone_max=2))
    zones = {1: 10, 2: 26, 3: 9}
    s = score_week(w, [run(0, minutes=45, zones=zones)], as_of=day(6)).sessions[0]
    assert s.execution == 80


def test_execution_unknown_without_heart_rate():
    w = week(Session(day(0), "easy", 45, zone_max=2))
    s = score_week(w, [run(0, minutes=45)], as_of=day(6)).sessions[0]
    assert s.execution is None


def test_scoring_without_provenance_is_refused(tmp_path):
    from coach.rules import DEFAULT_RULES_PATH, load_rules
    text = DEFAULT_RULES_PATH.read_text().replace("source: personal_choice\n      note: >\n      Asymmetric",
                                                   "note: >\n      Asymmetric")
    bad = tmp_path / "rules.yaml"
    bad.write_text(text)
    with pytest.raises(ValueError, match="scoring"):
        load_rules(bad)
