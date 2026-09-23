# tests/test_tokenstore.py
import pytest

from fitness_app.tokenstore import TokenStore, Tokens


@pytest.fixture
def store(tmp_path):
    return TokenStore(tmp_path / "tokens.sqlite")


def test_load_returns_none_when_no_row(store):
    assert store.load("whoop") is None


def test_save_then_load_round_trips(store):
    tokens = Tokens("acc", "ref", 1_800_000_000.0)
    store.save("whoop", tokens)
    assert store.load("whoop") == tokens


def test_save_overwrites_existing_row(store):
    store.save("whoop", Tokens("acc1", "ref1", 1.0))
    store.save("whoop", Tokens("acc2", "ref2", 2.0))
    assert store.load("whoop") == Tokens("acc2", "ref2", 2.0)


def test_rows_are_keyed_by_provider(store):
    store.save("whoop", Tokens("w", "w", 1.0))
    store.save("strava", Tokens("s", "s", 1.0))
    assert store.load("whoop").access_token == "w"
    assert store.load("strava").access_token == "s"


def test_rejected_save_leaves_old_row_untouched(store):
    old = Tokens("acc", "ref", 1.0)
    store.save("whoop", old)
    with pytest.raises(ValueError):
        store.save("whoop", Tokens("new", "", 2.0))  # empty refresh token
    assert store.load("whoop") == old


def test_default_path_honours_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FITNESS_DATA_DIR", str(tmp_path / "custom"))
    s = TokenStore()
    assert s.path == tmp_path / "custom" / "tokens.sqlite"
    assert s.path.parent.is_dir()


def test_refresh_lock_is_reentrant_safe_for_sequential_use(store):
    with store.refresh_lock():
        pass
    with store.refresh_lock():
        pass
