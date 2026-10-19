"""The service layer and the MCP surface. The key property: an agent cannot confirm."""
import asyncio
import json
from datetime import date

import pytest

from coach.checkins import CheckIn
from coach.service import Coach

PLAN = {
    "goal": "half", "race_date": "2027-03-14",
    "weeks": [{"start": "2026-10-19", "type": "foundation", "runs": 2, "km": 15,
               "sessions": [{"day": "2026-10-19", "kind": "easy", "target": 45, "zone_max": 2},
                            {"day": "2026-10-22", "kind": "easy", "target": 40}]}],
}
MON = date(2026, 10, 19)


@pytest.fixture
def coach(tmp_path):
    c = Coach(str(tmp_path / "coach.db"))
    proposal = c.propose(PLAN, "seed", author="user")
    c.confirm(proposal["version"], set())
    return c


def test_today_lists_sessions_and_gate(coach):
    t = coach.today(MON)
    assert t["sessions_today"][0]["target"] == 45
    assert [s["day"] for s in t["rest_of_week"]] == ["2026-10-22"]
    assert t["gate"]["run_go_max"] == 2 and t["days_to_race"] == 146


def test_proposal_stays_pending_until_a_human_confirms(coach):
    bigger = json.loads(json.dumps(PLAN))
    bigger["weeks"][0]["sessions"][0]["target"] = 60
    p = coach.propose(bigger, "more volume")
    assert p["status"] == "pending"
    assert coach.plan().sessions_on(MON)[0].target == 45   # plan in force unchanged


def test_week_score_accepts_connector_json(coach):
    strava = json.dumps({"activities": [{"sport_type": "Run", "start_local": "2026-10-19T07:00:00",
                                         "summary": {"distance": 6000, "moving_time": 2100}}]})
    out = coach.week_score(date(2026, 10, 25), strava, "[]")
    assert [s["status"] for s in out["sessions"]] == ["short", "missed"]


def test_check_in_round_trip(coach):
    coach.record_check_in(CheckIn(day=MON, decision="modify", reason="recovery 16%", adjusted_target=30))
    assert coach.today(MON)["checkin_today"]["adjusted_target"] == 30


def test_server_exposes_no_confirm_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DB", str(tmp_path / "server.db"))
    from coach import mcp_server
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert "propose_plan_change" in names and "record_check_in" in names
    assert not any("confirm" in n for n in names)


def test_server_refuses_a_check_in_that_adds_load(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DB", str(tmp_path / "server.db"))
    from coach import mcp_server
    monkeypatch.setattr(mcp_server, "coach", Coach(str(tmp_path / "server.db")))
    mcp_server.coach.confirm(mcp_server.coach.propose(PLAN, "seed", author="user")["version"], set())
    out = json.loads(mcp_server.record_check_in("modify", "feel great", day="2026-10-19", adjusted_target=70))
    assert "easier" in out["refused"]


def test_cli_propose_then_confirm(tmp_path, monkeypatch, capsys):
    import yaml
    from coach.__main__ import main
    monkeypatch.setenv("COACH_DB", str(tmp_path / "cli.db"))
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text(yaml.safe_dump(PLAN))
    assert main(["propose", str(plan_file), "--rationale", "first block"]) == 0
    assert main(["confirm", "1"]) == 0
    assert "confirmed" in capsys.readouterr().out
    assert main(["confirm", "1"]) == 1   # already confirmed


def test_tools_work_through_the_server_not_just_directly(tmp_path, monkeypatch):
    # Regression: the server runs tools on worker threads; SQLite refused cross-thread use.
    from coach import mcp_server
    monkeypatch.setattr(mcp_server, "coach", Coach(str(tmp_path / "server.db")))
    result = asyncio.run(mcp_server.mcp.call_tool("get_today", {"day": "2026-10-19"}))
    assert "Monday" in str(result)
