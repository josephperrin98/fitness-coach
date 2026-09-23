# tests/test_whoop_cli.py
import time

import pytest

from fitness_app.tokenstore import TokenStore, Tokens
from fitness_app.whoop import __main__ as cli
from fitness_app.whoop import auth

CONFIG = auth.WhoopConfig("cid", "csecret", "http://localhost:8765/callback")


@pytest.fixture
def store(tmp_path):
    return TokenStore(tmp_path / "t.sqlite")


def test_main_exits_2_and_names_missing_config(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("WHOOP_CLIENT_ID", raising=False)
    monkeypatch.delenv("WHOOP_CLIENT_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env file here, so nothing can fill the gap
    assert cli.main(["status"]) == 2
    assert "WHOOP_CLIENT_ID" in capsys.readouterr().err


def test_auth_command_saves_tokens(store, monkeypatch):
    monkeypatch.setattr(auth, "new_state", lambda: "s1")
    monkeypatch.setattr(
        auth, "exchange_code",
        lambda config, code: Tokens("SECRET-ACCESS", "SECRET-REFRESH", time.time() + 3600),
    )
    printed = []
    pasted = "http://localhost:8765/callback?code=abc&state=s1"
    rc = cli.cmd_auth(
        CONFIG, store,
        input_fn=lambda prompt: pasted,
        print_fn=lambda *a: printed.append(" ".join(map(str, a))),
    )
    assert rc == 0
    assert store.load("whoop").access_token == "SECRET-ACCESS"
    assert any(auth.AUTHORIZE_URL in line for line in printed)
    assert "SECRET" not in "\n".join(printed)  # tokens are never printed


def test_auth_command_rejects_wrong_state(store, monkeypatch):
    monkeypatch.setattr(auth, "new_state", lambda: "s1")
    with pytest.raises(auth.AuthError):
        cli.cmd_auth(CONFIG, store, input_fn=lambda prompt: "http://x/?code=abc&state=zzz", print_fn=lambda *a: None)
    assert store.load("whoop") is None


def test_status_reports_missing_token(store):
    printed = []
    rc = cli.cmd_status(CONFIG, store, print_fn=lambda *a: printed.append(" ".join(map(str, a))))
    assert rc == 1
    assert any("fitness_app.whoop auth" in line for line in printed)


def test_status_reports_expiry_and_live_call_without_leaking_token(store, monkeypatch):
    store.save("whoop", Tokens("SECRET-ACCESS", "SECRET-REFRESH", time.time() + 1800))

    class FakeClient:
        def __init__(self, store, config): pass
        def get_profile(self): return {"first_name": "Joseph", "last_name": "P"}

    monkeypatch.setattr(cli, "WhoopClient", FakeClient)
    printed = []
    rc = cli.cmd_status(CONFIG, store, print_fn=lambda *a: printed.append(" ".join(map(str, a))))
    assert rc == 0
    text = "\n".join(printed)
    assert "expires in" in text and "min" in text
    assert "Joseph" in text
    assert "SECRET" not in text
