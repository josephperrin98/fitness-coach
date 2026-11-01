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
    assert actuals_from_strava([{"sport_type": "Curling", "start_local": "2026-10-19T10:00:00",
                                 "summary": {}}])[0].kind == "other"


def test_sports_seen_in_real_data_have_a_kind():
    # Names as the connectors actually send them, so the calendar stops saying "Other".
    strava = {"Kitesurf": "kite", "Walk": "walk", "Hike": "walk"}
    whoop = {"walking": "walk", "commuting": "walk", "kiteboarding": "kite", "paddle-tennis": "racket",
             "dance": "dance", "activity": "other"}
    for sport, kind in strava.items():
        row = {"sport_type": sport, "start_local": "2026-10-19T10:00:00", "summary": {}}
        assert actuals_from_strava([row])[0].kind == kind, sport
    for sport, kind in whoop.items():
        assert actuals_from_whoop([{"start": "2026-10-19T10:00", "sport": sport}])[0].kind == kind, sport


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


def test_dashboard_gives_today_and_program_what_they_draw():
    store = CheckInStore(":memory:")
    store.record(CheckIn(day=date(2026, 10, 21), decision="go", reason="fine", feel=6), PLAN)
    acts = merge(actuals_from_strava(STRAVA), actuals_from_whoop(WHOOP))
    recs = [{"date": "2026-10-21", "recovery": 72, "hrv": 61.0}]
    out = dashboard(PLAN, store, acts, recs, today=date(2026, 10, 21), weeks_back=1, weeks_ahead=0)

    assert out["last_session"] == {"date": "2026-10-21", "kind": "strength", "minutes": 40.0,
                                   "km": 0.0, "recovery": 72}
    assert out["next_session"]["date"] == "2026-10-23"
    assert out["next_session"]["session"]["kind"] == "easy"
    assert out["next_session"]["session"]["purpose"].startswith("Easy")
    assert out["route"] == [{"start": "2026-10-19", "type": "foundation", "km": 15}]
    wed = next(d for d in out["days"] if d["date"] == "2026-10-21")
    assert wed["checkin"]["feel"] == 6
    tue = next(d for d in out["days"] if d["date"] == "2026-10-20")
    assert tue["planned"][0]["purpose"].startswith("Team sport")


def test_walks_are_not_a_last_session():
    walk = [{"sport_type": "Walk", "start_local": "2026-10-22T12:00:00",
             "summary": {"distance": 3000, "moving_time": 1800}}]
    acts = actuals_from_strava(STRAVA + walk)
    out = dashboard(PLAN, CheckInStore(":memory:"), acts, [], today=date(2026, 10, 22),
                    weeks_back=1, weeks_ahead=0)
    assert out["last_session"]["kind"] == "football"


def test_dashboard_sends_the_score_unit():
    plan = plan_from_dict({
        "goal": "half", "race_date": "2027-03-14",
        "weeks": [{"start": "2026-10-19", "type": "foundation", "runs": 1, "km": 10,
                   "sessions": [{"day": "2026-10-24", "kind": "long", "target": 10, "unit": "km"}]}],
    })
    out = dashboard(plan, CheckInStore(":memory:"), [], [], today=date(2026, 10, 21),
                    weeks_back=1, weeks_ahead=0)
    sat = next(d for d in out["days"] if d["date"] == "2026-10-24")
    assert sat["planned"][0]["score"]["unit"] == "km"


def test_dashboard_with_no_plan_and_no_activities_has_no_sessions():
    out = dashboard(None, CheckInStore(":memory:"), [], [], today=date(2026, 10, 21))
    assert out["last_session"] is None
    assert out["next_session"] is None
    assert out["route"] == []
