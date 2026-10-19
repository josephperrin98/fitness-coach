"""Joining Strava and Whoop rows, and the dashboard views built on them."""
from datetime import date

from coach.checkins import CheckIn, CheckInStore
from coach.plan import plan_from_dict
from coach.sources import actuals_from_strava, actuals_from_whoop, merge
from coach.views import activity_cost, dashboard

STRAVA = [
    {"sport_type": "Run", "start_local": "2026-10-19T07:05:00",
     "summary": {"distance": 7800, "moving_time": 2100}},
    {"sport_type": "Soccer", "start_local": "2026-10-20T19:00:00",
     "summary": {"distance": 0, "moving_time": 5400}},
]
WHOOP = [
    {"start": "2026-10-19T07:03", "sport": "running", "minutes": 37.0, "strain": 9.8, "distance_km": None,
     "zone_minutes": {"0": 0, "1": 8, "2": 22, "3": 5, "4": 0, "5": 0}},
    {"start": "2026-10-20T19:02", "sport": "soccer", "minutes": 92.0, "strain": 15.1, "distance_km": None,
     "zone_minutes": {"0": 5, "1": 20, "2": 30, "3": 25, "4": 10, "5": 2}},
    {"start": "2026-10-21T12:00", "sport": "weightlifting", "minutes": 40.0, "strain": 6.0,
     "distance_km": None, "zone_minutes": None},
]
PLAN = plan_from_dict({
    "goal": "half", "race_date": "2027-03-14",
    "weeks": [{"start": "2026-10-19", "type": "foundation", "runs": 2, "km": 15, "football": 1,
               "sessions": [{"day": "2026-10-19", "kind": "easy", "target": 45, "zone_max": 2},
                            {"day": "2026-10-20", "kind": "football"},
                            {"day": "2026-10-23", "kind": "easy", "target": 40, "zone_max": 2}]}],
})


def test_strava_run_gets_whoop_heart_rate_zones():
    acts = merge(actuals_from_strava(STRAVA), actuals_from_whoop(WHOOP))
    run = next(a for a in acts if a.kind == "run")
    assert run.minutes == 35.0 and run.km == 7.8          # volume from Strava
    assert run.zone_minutes[2] == 22 and run.strain == 9.8  # intensity from Whoop
    assert [a.kind for a in acts] == ["run", "football", "strength"]   # Whoop-only kept


def test_far_apart_starts_are_not_joined():
    whoop = [{**WHOOP[0], "start": "2026-10-19T09:00"}]
    acts = merge(actuals_from_strava(STRAVA[:1]), actuals_from_whoop(whoop))
    assert len(acts) == 2


def test_unknown_sport_is_other():
    assert actuals_from_strava([{"sport_type": "Kitesurf", "start_local": "2026-10-19T10:00:00",
                                 "summary": {}}])[0].kind == "other"


def test_dashboard_scores_the_week_and_shows_check_in():
    store = CheckInStore(":memory:")
    store.record(CheckIn(day=date(2026, 10, 19), decision="modify", reason="low recovery",
                         adjusted_target=30), PLAN)
    acts = merge(actuals_from_strava(STRAVA), actuals_from_whoop(WHOOP))
    recs = [{"date": "2026-10-19", "recovery": 30, "hrv": 50.0}]
    out = dashboard(PLAN, store, acts, recs, today=date(2026, 10, 21), weeks_back=1, weeks_ahead=0)

    mon = next(d for d in out["days"] if d["date"] == "2026-10-19")
    score = mon["planned"][0]["score"]
    assert score["planned"] == 30 and score["adjusted"] and score["execution"] == 85.7
    assert mon["checkin"]["decision"] == "modify" and mon["recovery"] == 30
    fri = next(d for d in out["days"] if d["date"] == "2026-10-23")
    assert fri["planned"][0]["score"]["status"] == "upcoming"
    assert out["weeks"][0]["actual_km"] == 7.8 and out["weeks"][0]["football"] == 1
    assert out["goal"]["days_to_race"] == 144


def test_activity_cost_compares_next_morning_to_median():
    acts = actuals_from_whoop(WHOOP)
    recs = [{"date": "2026-10-19", "recovery": 60, "hrv": 100.0},
            {"date": "2026-10-20", "recovery": 70, "hrv": 110.0},   # after the run
            {"date": "2026-10-21", "recovery": 30, "hrv": 60.0},    # after football
            {"date": "2026-10-22", "recovery": 55, "hrv": 90.0}]    # after strength
    rows = {r["kind"]: r for r in activity_cost(acts, recs, PLAN)["rows"]}
    assert rows["football"]["hrv_change_pct"] == -36.8   # 60 vs median 95
    assert rows["run: easy"]["next_recovery"] == 70
    assert not rows["football"]["enough"]


def test_activity_cost_without_recovery_data():
    assert activity_cost([], [])["rows"] == []
