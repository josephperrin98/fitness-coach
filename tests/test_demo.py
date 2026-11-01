"""The demo data runs through the real scoring code and tells a story worth showing."""
from coach.demo import DEMO_TODAY, demo_dashboard


def test_demo_covers_ten_weeks_with_past_and_future():
    d = demo_dashboard()
    assert len(d["days"]) == 70 and len(d["weeks"]) == 10
    statuses = {s["score"]["status"] for day in d["days"] for s in day["planned"] if "score" in s}
    assert {"done", "short", "missed", "upcoming"} <= statuses


def test_demo_is_deterministic():
    assert demo_dashboard() == demo_dashboard()


def test_demo_has_enough_mornings_to_draw_activity_cost():
    rows = demo_dashboard()["activity_cost"]["rows"]
    assert any(r["enough"] for r in rows)
    assert {"rest", "football"} <= {r["kind"] for r in rows}


def test_demo_has_check_ins_and_no_future_recovery():
    days = {d["date"]: d for d in demo_dashboard()["days"]}
    assert days[DEMO_TODAY.isoformat()]["checkin"]["decision"] == "go"
    assert all(d["recovery"] is None for k, d in days.items() if k > DEMO_TODAY.isoformat())


def test_demo_follows_its_own_check_ins():
    days = {d["date"]: d for d in demo_dashboard()["days"]}
    assert days["2026-11-09"]["done"] == []                                  # rested
    assert days["2026-11-30"]["planned"][0]["score"]["status"] == "done"     # ran the smaller target


def test_demo_quality_sessions_carry_a_pace_band():
    quality = [s for d in demo_dashboard()["days"] for s in d["planned"] if s["kind"] == "quality"]
    assert quality and all(s["pace"] == "threshold" and s["pace_band"].endswith("/km") for s in quality)


def test_demo_has_a_last_and_next_session_and_a_route():
    d = demo_dashboard()
    assert d["last_session"]["date"] == "2026-12-07"
    assert d["next_session"]["date"] == "2026-12-09"
    assert len(d["route"]) == 3
    assert d["route"][0]["start"] == "2026-12-07" and d["route"][-1]["start"] == "2026-12-21"
