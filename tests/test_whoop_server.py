# tests/test_whoop_server.py
import pytest

from fitness_app.whoop import auth, server

RECOVERY = {
    "cycle_id": 93845, "sleep_id": "sl-1", "user_id": 10129,
    "created_at": "2026-09-15T11:25:44.774Z", "updated_at": "2026-09-15T11:25:44.774Z",
    "score_state": "SCORED",
    "score": {"user_calibrating": False, "recovery_score": 44.0, "resting_heart_rate": 64.0,
              "hrv_rmssd_milli": 31.813, "spo2_percentage": 95.7, "skin_temp_celsius": 33.7},
}

SLEEP = {
    "id": "sl-1", "start": "2026-09-14T22:10:00.000Z", "end": "2026-09-15T06:40:00.000Z",
    "nap": False, "score_state": "SCORED",
    "score": {
        "stage_summary": {"total_in_bed_time_milli": 30_600_000, "total_awake_time_milli": 1_800_000,
                          "total_light_sleep_time_milli": 14_400_000,
                          "total_slow_wave_sleep_time_milli": 7_200_000,
                          "total_rem_sleep_time_milli": 7_200_000, "disturbance_count": 3},
        "respiratory_rate": 14.2, "sleep_performance_percentage": 88.0,
        "sleep_consistency_percentage": 70.0, "sleep_efficiency_percentage": 94.0,
    },
}

WORKOUT = {
    "id": "wo-1", "start": "2026-09-15T07:00:00.000Z", "end": "2026-09-15T08:05:00.000Z",
    "sport_name": "running", "score_state": "SCORED",
    "score": {"strain": 12.4, "average_heart_rate": 152, "max_heart_rate": 178,
              "kilojoule": 3100.0, "distance_meter": 12_030.0, "altitude_gain_meter": 85.0},
}

CYCLE = {
    "id": 93845, "start": "2026-09-14T22:00:00.000Z", "end": "2026-09-15T22:00:00.000Z",
    "score_state": "SCORED",
    "score": {"strain": 14.1, "kilojoule": 9800.0, "average_heart_rate": 68, "max_heart_rate": 178},
}


def test_trim_recovery_keeps_coach_fields_only():
    assert server.trim_recovery(RECOVERY) == {
        "date": "2026-09-15T11:25:44.774Z", "cycle_id": 93845, "score_state": "SCORED",
        "recovery_score": 44.0, "hrv_rmssd_milli": 31.813,
        "resting_heart_rate": 64.0, "spo2_percentage": 95.7,
    }


def test_trim_recovery_tolerates_unscored_record():
    unscored = {**RECOVERY, "score_state": "PENDING_SCORE", "score": None}
    out = server.trim_recovery(unscored)
    assert out["score_state"] == "PENDING_SCORE"
    assert out["recovery_score"] is None


def test_trim_sleep_converts_milliseconds_to_hours():
    out = server.trim_sleep(SLEEP)
    assert out["start"] == SLEEP["start"] and out["end"] == SLEEP["end"]
    assert out["nap"] is False
    assert out["sleep_performance_percentage"] == 88.0
    assert out["sleep_efficiency_percentage"] == 94.0
    assert out["in_bed_hours"] == 8.5
    assert out["light_hours"] == 4.0
    assert out["slow_wave_hours"] == 2.0
    assert out["rem_hours"] == 2.0
    assert out["awake_hours"] == 0.5
    assert out["disturbance_count"] == 3
    assert out["respiratory_rate"] == 14.2


def test_trim_workout_converts_metres_to_km():
    out = server.trim_workout(WORKOUT)
    assert out == {
        "start": WORKOUT["start"], "end": WORKOUT["end"], "sport": "running",
        "score_state": "SCORED", "strain": 12.4, "average_heart_rate": 152,
        "max_heart_rate": 178, "distance_km": 12.03, "altitude_gain_m": 85.0,
        "kilojoule": 3100.0,
    }


def test_trim_cycle():
    assert server.trim_cycle(CYCLE) == {
        "start": CYCLE["start"], "end": CYCLE["end"], "score_state": "SCORED",
        "strain": 14.1, "average_heart_rate": 68, "max_heart_rate": 178, "kilojoule": 9800.0,
    }


class FakeClient:
    def get_recovery(self, days=7): return [RECOVERY]
    def get_sleep(self, days=7): return [SLEEP]
    def get_workouts(self, days=7): return [WORKOUT]
    def get_cycles(self, days=7): return [CYCLE]
    def get_profile(self): return {"user_id": 1, "first_name": "J", "last_name": "P", "email": "j@x"}
    def get_body_measurements(self): return {"height_meter": 1.8, "weight_kilogram": 75.0, "max_heart_rate": 190}


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(server, "_client", lambda: FakeClient())


def test_tools_return_trimmed_lists(fake_client):
    assert server.get_recovery(7) == [server.trim_recovery(RECOVERY)]
    assert server.get_sleep(7) == [server.trim_sleep(SLEEP)]
    assert server.get_workouts(7) == [server.trim_workout(WORKOUT)]
    assert server.get_cycles(7) == [server.trim_cycle(CYCLE)]


def test_profile_tool_drops_email(fake_client):
    assert server.get_profile() == {"first_name": "J", "last_name": "P"}


def test_body_tool_passes_through(fake_client):
    assert server.get_body_measurements() == {
        "height_meter": 1.8, "weight_kilogram": 75.0, "max_heart_rate": 190,
    }


def test_missing_token_surfaces_relogin_instruction(monkeypatch):
    class Unauthorised:
        def get_recovery(self, days=7):
            raise auth.AuthError(auth.RELOGIN)
    monkeypatch.setattr(server, "_client", lambda: Unauthorised())
    with pytest.raises(auth.AuthError, match="fitness_app.whoop auth"):
        server.get_recovery(7)


def test_create_server_registers_six_tools():
    mcp = server.create_server()
    names = {t.name for t in mcp._tool_manager.list_tools()}
    assert names == {
        "get_recovery", "get_sleep", "get_workouts", "get_cycles",
        "get_profile", "get_body_measurements",
    }
