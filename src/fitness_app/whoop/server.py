# src/fitness_app/whoop/server.py
"""MCP adapter: six tools, one per client method, each trimmed to what a
coach needs. Knows nothing about OAuth.

Tools are plain functions registered in `create_server()` so tests can
call them directly. mcp 2.x shows the model an exception's message only
if it is a `ToolError`; anything else is reported as a bare crash. So
`create_server()` re-raises the failures we expect (auth, config, HTTP) as
`ToolError` — that is how the re-login instruction in `AuthError` reaches
the model.
"""

import functools

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from fitness_app import http
from fitness_app.tokenstore import TokenStore
from fitness_app.whoop.auth import AuthError, ConfigError, WhoopConfig
from fitness_app.whoop.client import WhoopClient


def _client() -> WhoopClient:
    return WhoopClient(TokenStore(), WhoopConfig.from_env())


def _hours(milliseconds) -> float | None:
    return None if milliseconds is None else round(milliseconds / 3_600_000, 2)


def _km(metres) -> float | None:
    return None if metres is None else round(metres / 1000, 2)


def trim_recovery(r: dict) -> dict:
    s = r.get("score") or {}
    return {
        "date": r.get("created_at"),
        "cycle_id": r.get("cycle_id"),
        "score_state": r.get("score_state"),
        "recovery_score": s.get("recovery_score"),
        "hrv_rmssd_milli": s.get("hrv_rmssd_milli"),
        "resting_heart_rate": s.get("resting_heart_rate"),
        "spo2_percentage": s.get("spo2_percentage"),
    }


def trim_sleep(r: dict) -> dict:
    s = r.get("score") or {}
    stages = s.get("stage_summary") or {}
    return {
        "start": r.get("start"),
        "end": r.get("end"),
        "nap": r.get("nap"),
        "score_state": r.get("score_state"),
        "sleep_performance_percentage": s.get("sleep_performance_percentage"),
        "sleep_efficiency_percentage": s.get("sleep_efficiency_percentage"),
        "sleep_consistency_percentage": s.get("sleep_consistency_percentage"),
        "in_bed_hours": _hours(stages.get("total_in_bed_time_milli")),
        "awake_hours": _hours(stages.get("total_awake_time_milli")),
        "light_hours": _hours(stages.get("total_light_sleep_time_milli")),
        "slow_wave_hours": _hours(stages.get("total_slow_wave_sleep_time_milli")),
        "rem_hours": _hours(stages.get("total_rem_sleep_time_milli")),
        "disturbance_count": stages.get("disturbance_count"),
        "respiratory_rate": s.get("respiratory_rate"),
    }


def trim_workout(r: dict) -> dict:
    s = r.get("score") or {}
    return {
        "start": r.get("start"),
        "end": r.get("end"),
        "sport": r.get("sport_name") or r.get("sport_id"),
        "score_state": r.get("score_state"),
        "strain": s.get("strain"),
        "average_heart_rate": s.get("average_heart_rate"),
        "max_heart_rate": s.get("max_heart_rate"),
        "distance_km": _km(s.get("distance_meter")),
        "altitude_gain_m": s.get("altitude_gain_meter"),
        "kilojoule": s.get("kilojoule"),
    }


def trim_cycle(r: dict) -> dict:
    s = r.get("score") or {}
    return {
        "start": r.get("start"),
        "end": r.get("end"),
        "score_state": r.get("score_state"),
        "strain": s.get("strain"),
        "average_heart_rate": s.get("average_heart_rate"),
        "max_heart_rate": s.get("max_heart_rate"),
        "kilojoule": s.get("kilojoule"),
    }


def get_recovery(days: int = 7) -> list[dict]:
    """Daily WHOOP recovery for the last `days` days: recovery score (0-100),
    HRV (ms), resting heart rate, SpO2. Newest first."""
    return [trim_recovery(r) for r in _client().get_recovery(days)]


def get_sleep(days: int = 7) -> list[dict]:
    """Sleep sessions for the last `days` days: performance %, efficiency %,
    hours per stage, disturbances, respiratory rate. Newest first."""
    return [trim_sleep(r) for r in _client().get_sleep(days)]


def get_workouts(days: int = 7) -> list[dict]:
    """Workouts for the last `days` days: sport, strain, heart rate, distance
    (km), elevation gain (m). Newest first."""
    return [trim_workout(r) for r in _client().get_workouts(days)]


def get_cycles(days: int = 7) -> list[dict]:
    """Physiological cycles (roughly one per day) for the last `days` days:
    day strain and heart rate. Newest first."""
    return [trim_cycle(r) for r in _client().get_cycles(days)]


def get_profile() -> dict:
    """The athlete's first and last name."""
    p = _client().get_profile()
    return {"first_name": p.get("first_name"), "last_name": p.get("last_name")}


def get_body_measurements() -> dict:
    """Height (m), weight (kg) and max heart rate as recorded in WHOOP."""
    return _client().get_body_measurements()


TOOLS = (get_recovery, get_sleep, get_workouts, get_cycles, get_profile, get_body_measurements)
EXPECTED_ERRORS = (AuthError, ConfigError, http.HttpError)


def _surface_errors(tool):
    """Re-raise expected failures as `ToolError` so their message reaches the model."""

    @functools.wraps(tool)
    def wrapper(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except EXPECTED_ERRORS as e:
            raise ToolError(str(e)) from e

    return wrapper


def create_server() -> MCPServer:
    mcp = MCPServer("whoop")
    for tool in TOOLS:
        mcp.tool()(_surface_errors(tool))
    return mcp
