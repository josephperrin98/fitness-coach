# tests/test_whoop_auth.py
import time
import urllib.parse

import pytest

from fitness_app import http
from fitness_app.tokenstore import TokenStore, Tokens
from fitness_app.whoop import auth

CONFIG = auth.WhoopConfig("cid", "csecret", "http://localhost:8765/callback")


@pytest.fixture
def store(tmp_path):
    return TokenStore(tmp_path / "t.sqlite")


@pytest.fixture
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network call was not expected")
    monkeypatch.setattr(http, "post_form", boom)


# --- config ---------------------------------------------------------------

def test_from_env_names_missing_variables(monkeypatch):
    monkeypatch.delenv("WHOOP_CLIENT_ID", raising=False)
    monkeypatch.setenv("WHOOP_CLIENT_SECRET", "s")
    with pytest.raises(auth.ConfigError) as e:
        auth.WhoopConfig.from_env()
    assert "WHOOP_CLIENT_ID" in str(e.value)


def test_from_env_reads_values_and_default_redirect(monkeypatch):
    monkeypatch.setenv("WHOOP_CLIENT_ID", "id")
    monkeypatch.setenv("WHOOP_CLIENT_SECRET", "sec")
    monkeypatch.delenv("WHOOP_REDIRECT_URI", raising=False)
    cfg = auth.WhoopConfig.from_env()
    assert cfg == auth.WhoopConfig("id", "sec", "http://localhost:8765/callback")


# --- authorize URL and redirect --------------------------------------------

def test_authorize_url_carries_all_scopes_and_state():
    url = auth.authorize_url(CONFIG, "xyz")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    assert url.startswith(auth.AUTHORIZE_URL)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["cid"]
    assert q["redirect_uri"] == ["http://localhost:8765/callback"]
    assert q["state"] == ["xyz"]
    scopes = set(q["scope"][0].split())
    assert scopes == {
        "read:recovery", "read:sleep", "read:cycles", "read:workout",
        "read:profile", "read:body_measurement", "offline",
    }


def test_parse_redirect_extracts_code():
    pasted = "http://localhost:8765/callback?code=abc123&state=xyz&scope=offline"
    assert auth.parse_redirect(pasted, "xyz") == "abc123"


def test_parse_redirect_rejects_wrong_state():
    with pytest.raises(auth.AuthError, match="state"):
        auth.parse_redirect("http://localhost:8765/callback?code=abc&state=other", "xyz")


def test_parse_redirect_requires_code():
    with pytest.raises(auth.AuthError, match="code"):
        auth.parse_redirect("http://localhost:8765/callback?state=xyz", "xyz")


# --- token exchange and refresh --------------------------------------------

def test_exchange_code_posts_grant_and_returns_tokens(monkeypatch):
    calls = []

    def fake_post(url, data, headers=None):
        calls.append((url, data))
        return {"access_token": "A", "refresh_token": "R", "expires_in": 3600}

    monkeypatch.setattr(http, "post_form", fake_post)
    before = time.time()
    tokens = auth.exchange_code(CONFIG, "abc")
    assert tokens.access_token == "A" and tokens.refresh_token == "R"
    assert before + 3600 <= tokens.expires_at <= time.time() + 3600
    url, data = calls[0]
    assert url == auth.TOKEN_URL
    assert data["grant_type"] == "authorization_code"
    assert data["code"] == "abc"
    assert data["client_id"] == "cid"
    assert data["client_secret"] == "csecret"
    assert data["redirect_uri"] == CONFIG.redirect_uri


def test_missing_refresh_token_in_response_is_an_auth_error(monkeypatch):
    monkeypatch.setattr(http, "post_form", lambda *a, **k: {"access_token": "A", "expires_in": 1})
    with pytest.raises(auth.AuthError, match="offline"):
        auth.exchange_code(CONFIG, "abc")


def test_valid_token_returns_stored_when_fresh(store, no_network):
    store.save("whoop", Tokens("A", "R", time.time() + 3600))
    assert auth.valid_access_token(store, CONFIG) == "A"


def test_valid_token_refreshes_and_persists_rotated_pair(store, monkeypatch):
    store.save("whoop", Tokens("old", "old-refresh", time.time() - 10))
    calls = []

    def fake_post(url, data, headers=None):
        calls.append(data)
        return {"access_token": "new", "refresh_token": "new-refresh", "expires_in": 3600}

    monkeypatch.setattr(http, "post_form", fake_post)
    assert auth.valid_access_token(store, CONFIG) == "new"
    assert len(calls) == 1
    assert calls[0]["grant_type"] == "refresh_token"
    assert calls[0]["refresh_token"] == "old-refresh"
    saved = store.load("whoop")
    assert saved.refresh_token == "new-refresh"  # the rotation was persisted
    assert saved.access_token == "new"


def test_valid_token_refreshes_within_margin(store, monkeypatch):
    store.save("whoop", Tokens("A", "R", time.time() + 30))  # < 60 s margin
    monkeypatch.setattr(
        http, "post_form",
        lambda *a, **k: {"access_token": "B", "refresh_token": "R2", "expires_in": 3600},
    )
    assert auth.valid_access_token(store, CONFIG) == "B"


def test_valid_token_forces_refresh_when_token_was_rejected(store, monkeypatch):
    store.save("whoop", Tokens("A", "R", time.time() + 3600))
    monkeypatch.setattr(
        http, "post_form",
        lambda *a, **k: {"access_token": "B", "refresh_token": "R2", "expires_in": 3600},
    )
    assert auth.valid_access_token(store, CONFIG, rejected="A") == "B"


def test_valid_token_reuses_refresh_done_by_someone_else(store, monkeypatch):
    # Stored token was rejected, but by the time we hold the lock the row
    # already holds a different, fresh token: use it, do not refresh again.
    store.save("whoop", Tokens("B", "R2", time.time() + 3600))

    def boom(*a, **k):
        raise AssertionError("must not refresh")
    monkeypatch.setattr(http, "post_form", boom)
    assert auth.valid_access_token(store, CONFIG, rejected="A") == "B"


def test_rejected_refresh_raises_with_relogin_instruction(store, monkeypatch):
    store.save("whoop", Tokens("A", "dead", time.time() - 10))

    def fake_post(url, data, headers=None):
        raise http.HttpError(400, "/oauth/oauth2/token", body='{"error":"invalid_grant"}')

    monkeypatch.setattr(http, "post_form", fake_post)
    with pytest.raises(auth.AuthError) as e:
        auth.valid_access_token(store, CONFIG)
    assert "invalid_grant" in str(e.value)
    assert "fitness_app.whoop auth" in str(e.value)
    assert store.load("whoop").refresh_token == "dead"  # stale row left in place


def test_no_row_raises_relogin(store, no_network):
    with pytest.raises(auth.AuthError, match="fitness_app.whoop auth"):
        auth.valid_access_token(store, CONFIG)
