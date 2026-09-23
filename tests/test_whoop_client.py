# tests/test_whoop_client.py
import pytest

from fitness_app import http
from fitness_app.whoop import auth
from fitness_app.whoop.client import API_BASE, MAX_PAGES, WhoopClient

CONFIG = auth.WhoopConfig("cid", "csecret", "http://localhost:8765/callback")


class FakeAuth:
    """Stands in for auth.valid_access_token; records the `rejected` values."""

    def __init__(self):
        self.calls = []

    def __call__(self, store, config, rejected=None):
        self.calls.append(rejected)
        return "tok2" if rejected else "tok1"


@pytest.fixture
def fake_auth(monkeypatch):
    fa = FakeAuth()
    monkeypatch.setattr(auth, "valid_access_token", fa)
    return fa


@pytest.fixture
def client():
    return WhoopClient(store=object(), config=CONFIG)


def test_profile_sends_bearer_header(client, fake_auth, monkeypatch):
    seen = {}

    def fake_get(url, params=None, headers=None):
        seen.update(url=url, params=params, headers=headers)
        return {"user_id": 1, "first_name": "J"}

    monkeypatch.setattr(http, "get_json", fake_get)
    assert client.get_profile() == {"user_id": 1, "first_name": "J"}
    assert seen["url"] == API_BASE + "/user/profile/basic"
    assert seen["headers"] == {"Authorization": "Bearer tok1"}
    assert seen["params"] is None


def test_recovery_builds_window_and_follows_pagination(client, fake_auth, monkeypatch):
    pages = [
        {"records": [{"id": 1}, {"id": 2}], "next_token": "p2"},
        {"records": [{"id": 3}], "next_token": None},
    ]
    calls = []

    def fake_get(url, params=None, headers=None):
        calls.append((url, dict(params)))
        return pages[len(calls) - 1]

    monkeypatch.setattr(http, "get_json", fake_get)
    records = client.get_recovery(days=7)
    assert [r["id"] for r in records] == [1, 2, 3]
    assert len(calls) == 2
    first_url, first_params = calls[0]
    assert first_url == API_BASE + "/recovery"
    assert first_params["limit"] == 25
    assert first_params["start"].endswith("Z") and first_params["end"].endswith("Z")
    assert "nextToken" not in first_params
    assert calls[1][1]["nextToken"] == "p2"


def test_pagination_stops_at_cap(client, fake_auth, monkeypatch):
    count = {"n": 0}

    def fake_get(url, params=None, headers=None):
        count["n"] += 1
        return {"records": [{"id": count["n"]}], "next_token": "more"}

    monkeypatch.setattr(http, "get_json", fake_get)
    records = client.get_sleep(days=30)
    assert count["n"] == MAX_PAGES
    assert len(records) == MAX_PAGES


def test_401_triggers_exactly_one_refresh_and_one_retry(client, fake_auth, monkeypatch):
    attempts = []

    def fake_get(url, params=None, headers=None):
        attempts.append(headers["Authorization"])
        if len(attempts) == 1:
            raise http.HttpError(401, "/v2/user/profile/basic")
        return {"user_id": 1}

    monkeypatch.setattr(http, "get_json", fake_get)
    assert client.get_profile() == {"user_id": 1}
    assert attempts == ["Bearer tok1", "Bearer tok2"]
    assert fake_auth.calls == [None, "tok1"]


def test_second_401_propagates(client, fake_auth, monkeypatch):
    def fake_get(url, params=None, headers=None):
        raise http.HttpError(401, "/v2/user/profile/basic")

    monkeypatch.setattr(http, "get_json", fake_get)
    with pytest.raises(http.HttpError) as e:
        client.get_profile()
    assert e.value.status == 401
    assert fake_auth.calls == [None, "tok1"]


def test_non_401_errors_propagate_without_refresh(client, fake_auth, monkeypatch):
    def fake_get(url, params=None, headers=None):
        raise http.HttpError(429, "/v2/recovery")

    monkeypatch.setattr(http, "get_json", fake_get)
    with pytest.raises(http.HttpError) as e:
        client.get_recovery()
    assert e.value.status == 429
    assert fake_auth.calls == [None]


def test_endpoint_paths(client, fake_auth, monkeypatch):
    urls = []

    def fake_get(url, params=None, headers=None):
        urls.append(url)
        return {"records": []}

    monkeypatch.setattr(http, "get_json", fake_get)
    client.get_recovery(); client.get_sleep(); client.get_workouts(); client.get_cycles()
    client.get_body_measurements()
    assert urls == [
        API_BASE + "/recovery",
        API_BASE + "/activity/sleep",
        API_BASE + "/activity/workout",
        API_BASE + "/cycle",
        API_BASE + "/user/measurement/body",
    ]
