# Whoop MCP and Converse A — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> If the superpowers plugin is not installed in this environment, follow the tasks in order by hand — every step is self-contained.

**Goal:** A Whoop MCP server built from the standard library plus the `mcp` SDK, so that Claude Code in the Codespace can answer "how recovered am I this week?" from real data.

**Architecture:** Two generic modules (`http.py`, `tokenstore.py`) under a `whoop/` subpackage split into `auth` (OAuth), `client` (endpoints + pagination), `server` (thin MCP adapter) and a CLI (`auth | status | serve`). The client knows nothing about MCP; the server knows nothing about OAuth. Tests fake `http.py` and never touch the network.

**Tech Stack:** Python 3.12, `uv`, `mcp` (runtime), `pytest` (dev). Everything else is stdlib: `urllib`, `sqlite3`, `threading`, `argparse`, `dataclasses`.

**Spec:** `docs/specs/2026-09-17-whoop-mcp-converse-a-design.md` — read it first; this plan argues from it.

## Global Constraints

- Python `>=3.12`. Runtime dependency: `mcp` only. Dev dependency: `pytest` only.
- `src/` layout; package name `fitness_app`; Whoop code under `fitness_app/whoop/`.
- Secrets from the environment only. Never log, print or return a token, a client secret, or a request/response body.
- **In `serve` mode stdout is the MCP protocol channel.** All logging goes to stderr. Never `print()` from server code.
- Commit after every task. Conventional Commits with scope: `feat(whoop):`, `feat(core):`, `test(...)`, `chore:`, `docs:`. End each commit body with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Run the full suite (`uv run pytest -q`) before starting a task and before every commit.
- Scopes, verbatim: `read:recovery read:sleep read:cycles read:workout read:profile read:body_measurement offline`.
- Redirect URI default, verbatim: `http://localhost:8765/callback`.
- Pagination: page size 25, at most 20 pages.
- Refresh margin: 60 seconds. SQLite timeout: 5 seconds.

## File Structure

Already present from the bootstrap (created on the owner's machine before the first push):

```
.devcontainer/devcontainer.json   # Codespace recipe
.mcp.json                         # runs `uv run python -m fitness_app.whoop`
CLAUDE.md                         # coach persona for Converse A
PRIVACY.md, README.md, .env.example, .gitignore
pyproject.toml                    # deps declared; uv.lock is created in Task 1
src/fitness_app/__init__.py       # empty
src/fitness_app/whoop/__init__.py # empty
docs/whoop-app-setup.md, docs/specs/, docs/plans/, docs/decisions/
```

Created by this plan, one responsibility each:

| File | Responsibility |
|---|---|
| `src/fitness_app/http.py` | `get_json`, `post_form` over `urllib`; `HttpError`; logs path+status only |
| `src/fitness_app/tokenstore.py` | `Tokens` dataclass; `TokenStore.load/save` (one transaction); `refresh_lock()` |
| `src/fitness_app/env.py` | `load_dotenv()` — reads `.env` into `os.environ` if present (local dev only) |
| `src/fitness_app/whoop/auth.py` | `WhoopConfig`, authorize URL, redirect parsing, code exchange, refresh, `valid_access_token` |
| `src/fitness_app/whoop/client.py` | `WhoopClient`: six endpoints, date window, pagination, 401→refresh→retry |
| `src/fitness_app/whoop/server.py` | `trim_*` functions, six tool functions, `create_server()` |
| `src/fitness_app/whoop/__main__.py` | CLI: `auth`, `status`, `serve` |
| `tests/test_*.py` | one test file per module |
| `docs/decisions/0001-strava-integration.md` | outcome of the Strava spike |

---

### Task 1: Environment check and first green test

**Files:**
- Create: `tests/test_smoke.py`
- Create: `uv.lock` (generated)

**Interfaces:**
- Consumes: `pyproject.toml` from the bootstrap.
- Produces: a working `uv run pytest` loop that every later task relies on.

- [ ] **Step 1: Confirm the toolchain**

Run:
```bash
python --version && uv --version && claude --version
```
Expected: Python 3.12.x, a uv version, a Claude Code version. If `uv` is missing: `pip install --user uv`. If `claude` is missing: `npm install -g @anthropic-ai/claude-code`.

- [ ] **Step 2: Install dependencies and generate the lockfile**

Run:
```bash
uv sync
```
Expected: creates `.venv/` and `uv.lock`; installs `mcp` and `pytest`; installs `fitness_app` in editable mode.

- [ ] **Step 3: Write the smoke test**

```python
# tests/test_smoke.py
"""Proves the package is importable from the installed environment."""
import fitness_app
import fitness_app.whoop


def test_package_imports():
    assert fitness_app is not None
    assert fitness_app.whoop is not None
```

- [ ] **Step 4: Run it**

Run: `uv run pytest -q`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add uv.lock tests/test_smoke.py
git commit -m "chore: lock dependencies and add smoke test

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `http.py` — minimal HTTP over urllib

**Files:**
- Create: `src/fitness_app/http.py`
- Test: `tests/test_http.py`

**Interfaces:**
- Produces:
  - `class HttpError(Exception)` with attributes `status: int`, `path: str`, `body: str`. `status == 0` means a network error.
  - `get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict`
  - `post_form(url: str, data: dict, headers: dict | None = None) -> dict`
  - Every later module calls these as `http.get_json(...)` / `http.post_form(...)` after `from fitness_app import http`, so tests can `monkeypatch.setattr(http, "get_json", fake)`.

Per the spec, the network path of this module is not unit-tested (it would mean faking `urllib`); the `status` command is its live check. Two small tests cover what *is* logic: the error message and the log-safe path.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_http.py
from fitness_app import http


def test_http_error_message_names_status_and_path():
    err = http.HttpError(500, "/v2/recovery", body="boom")
    assert str(err) == "HTTP 500 on /v2/recovery"
    assert err.status == 500
    assert err.body == "boom"


def test_network_error_message():
    err = http.HttpError(0, "/v2/recovery", body="network error: timed out")
    assert str(err) == "Network error on /v2/recovery: network error: timed out"


def test_log_path_strips_query_string():
    # Query strings carry pagination tokens and, on the auth redirect, a code.
    # Nothing after '?' may ever reach a log line.
    assert http._log_path("https://x.test/v2/recovery?nextToken=abc&limit=25") == "/v2/recovery"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_http.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fitness_app.http'`.

- [ ] **Step 3: Implement**

```python
# src/fitness_app/http.py
"""Minimal HTTP helpers over urllib.

Knows nothing about authentication. Logs method, path and status only —
never headers, bodies or query strings.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


class HttpError(Exception):
    """A non-2xx response (status > 0) or a network failure (status == 0)."""

    def __init__(self, status: int, path: str, body: str = ""):
        self.status = status
        self.path = path
        self.body = body
        if status == 0:
            message = f"Network error on {path}: {body}"
        else:
            message = f"HTTP {status} on {path}"
        super().__init__(message)


def _log_path(url: str) -> str:
    """Path component only, so nothing sensitive is ever logged."""
    return urllib.parse.urlsplit(url).path


def _send(req: urllib.request.Request) -> dict:
    path = _log_path(req.full_url)
    method = req.get_method()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            log.info("%s %s -> %s", method, path, resp.status)
            raw = resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        log.info("%s %s -> %s", method, path, e.code)
        raise HttpError(e.code, path, body) from None
    except urllib.error.URLError as e:
        raise HttpError(0, path, f"network error: {e.reason}") from None
    return json.loads(raw) if raw else {}


def get_json(url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    return _send(req)


def post_form(url: str, data: dict, headers: dict | None = None) -> dict:
    body = urllib.parse.urlencode(data).encode()
    merged = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=merged, method="POST")
    return _send(req)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest -q`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/fitness_app/http.py tests/test_http.py
git commit -m "feat(core): add urllib-based HTTP helpers with log-safe errors

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `tokenstore.py` — SQLite token persistence

**Files:**
- Create: `src/fitness_app/tokenstore.py`
- Test: `tests/test_tokenstore.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Tokens: access_token: str; refresh_token: str; expires_at: float` (unix seconds, UTC).
  - `class TokenStore(path: Path | None = None)` — default path `$FITNESS_DATA_DIR/tokens.sqlite`, falling back to `.data/tokens.sqlite`. Creates the directory and table.
  - `TokenStore.load(provider: str) -> Tokens | None`
  - `TokenStore.save(provider: str, tokens: Tokens) -> None` — one transaction; raises `ValueError` before touching the DB if either token is empty.
  - `TokenStore.refresh_lock()` — context manager; serialises refreshes within one process.
  - `TokenStore.path: Path`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_tokenstore.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fitness_app.tokenstore'`.

- [ ] **Step 3: Implement**

```python
# src/fitness_app/tokenstore.py
"""Persist OAuth tokens, one row per provider, in SQLite.

`save` is a single transaction so a rotated refresh token is never
half-written. `refresh_lock` serialises refreshes within a process; the
SQLite busy timeout covers a second process.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SQLITE_TIMEOUT_SECONDS = 5

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tokens (
    provider      TEXT PRIMARY KEY,
    access_token  TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at    REAL NOT NULL
)
"""

_UPSERT = """
INSERT INTO tokens (provider, access_token, refresh_token, expires_at)
VALUES (?, ?, ?, ?)
ON CONFLICT(provider) DO UPDATE SET
    access_token  = excluded.access_token,
    refresh_token = excluded.refresh_token,
    expires_at    = excluded.expires_at
"""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str
    expires_at: float  # unix seconds, UTC


def default_path() -> Path:
    return Path(os.environ.get("FITNESS_DATA_DIR", ".data")) / "tokens.sqlite"


class TokenStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._transaction() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _transaction(self):
        conn = sqlite3.connect(self.path, timeout=SQLITE_TIMEOUT_SECONDS)
        try:
            with conn:  # commits on success, rolls back on exception
                yield conn
        finally:
            conn.close()

    def load(self, provider: str) -> Tokens | None:
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT access_token, refresh_token, expires_at FROM tokens WHERE provider = ?",
                (provider,),
            ).fetchone()
        return Tokens(*row) if row else None

    def save(self, provider: str, tokens: Tokens) -> None:
        if not tokens.access_token or not tokens.refresh_token:
            raise ValueError("refusing to save empty tokens")
        with self._transaction() as conn:
            conn.execute(
                _UPSERT,
                (provider, tokens.access_token, tokens.refresh_token, tokens.expires_at),
            )

    @contextmanager
    def refresh_lock(self):
        with self._lock:
            yield
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest -q`
Expected: `11 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/fitness_app/tokenstore.py tests/test_tokenstore.py
git commit -m "feat(core): add SQLite token store with atomic save and refresh lock

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `env.py` and `whoop/auth.py` — configuration and OAuth

**Files:**
- Create: `src/fitness_app/env.py`
- Create: `src/fitness_app/whoop/auth.py`
- Test: `tests/test_env.py`, `tests/test_whoop_auth.py`

**Interfaces:**
- Consumes: `http.post_form`, `http.HttpError`, `TokenStore`, `Tokens`.
- Produces:
  - `env.load_dotenv(path: str | Path = ".env") -> None` — sets `os.environ` keys that are not already set; silently does nothing if the file is absent.
  - `auth.PROVIDER = "whoop"`, `auth.SCOPES`, `auth.AUTHORIZE_URL`, `auth.TOKEN_URL`, `auth.RELOGIN` (the instruction string), `auth.REFRESH_MARGIN_SECONDS = 60`.
  - `class ConfigError(Exception)`, `class AuthError(Exception)`.
  - `@dataclass(frozen=True) class WhoopConfig: client_id, client_secret, redirect_uri` with `WhoopConfig.from_env() -> WhoopConfig` (raises `ConfigError` naming missing variables).
  - `new_state() -> str`
  - `authorize_url(config: WhoopConfig, state: str) -> str`
  - `parse_redirect(pasted_url: str, expected_state: str) -> str` (returns the code)
  - `exchange_code(config, code: str) -> Tokens`
  - `refresh(config, tokens: Tokens) -> Tokens`
  - `valid_access_token(store: TokenStore, config: WhoopConfig, rejected: str | None = None) -> str` — `rejected` is an access token the API just refused with 401; if the stored token equals it, refresh even though it looks fresh.

- [ ] **Step 1: Write the failing tests for `env.py`**

```python
# tests/test_env.py
from fitness_app import env


def test_load_dotenv_sets_missing_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_A", raising=False)
    (tmp_path / ".env").write_text('DEMO_A=hello\n# comment\n\nDEMO_B="quoted"\n')
    env.load_dotenv(tmp_path / ".env")
    import os
    assert os.environ["DEMO_A"] == "hello"
    assert os.environ["DEMO_B"] == "quoted"
    monkeypatch.delenv("DEMO_A")
    monkeypatch.delenv("DEMO_B")


def test_load_dotenv_does_not_override_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_A", "from-shell")
    (tmp_path / ".env").write_text("DEMO_A=from-file\n")
    env.load_dotenv(tmp_path / ".env")
    import os
    assert os.environ["DEMO_A"] == "from-shell"


def test_load_dotenv_ignores_missing_file(tmp_path):
    env.load_dotenv(tmp_path / "nope")  # must not raise
```

- [ ] **Step 2: Write the failing tests for `auth.py`**

```python
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
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_env.py tests/test_whoop_auth.py -q`
Expected: FAIL with `ModuleNotFoundError` for `fitness_app.env` and `fitness_app.whoop.auth`.

- [ ] **Step 4: Implement `env.py`**

```python
# src/fitness_app/env.py
"""Load a local `.env` file into the environment, for development only.

In the Codespace, secrets arrive as real environment variables and this is
a no-op. Existing variables always win over the file.
"""

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
```

- [ ] **Step 5: Implement `auth.py`**

```python
# src/fitness_app/whoop/auth.py
"""WHOOP OAuth 2.0: authorize URL, code exchange, refresh, and the one
function everything else calls — `valid_access_token`.

WHOOP rotates refresh tokens on every refresh and invalidates the old one,
so the new pair must be persisted before anything else happens. Refreshes
are serialised through the store's lock; after taking it we re-read the row
because another caller may have refreshed first.
"""

import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass

from fitness_app import http
from fitness_app.tokenstore import TokenStore, Tokens

PROVIDER = "whoop"
AUTHORIZE_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
SCOPES = (
    "read:recovery read:sleep read:cycles read:workout "
    "read:profile read:body_measurement offline"
)
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"
REFRESH_MARGIN_SECONDS = 60
RELOGIN = "Not authorised with WHOOP. Run `uv run python -m fitness_app.whoop auth` first."


class ConfigError(Exception):
    """Required configuration is missing."""


class AuthError(Exception):
    """Authorisation failed; the message says what to do next."""


@dataclass(frozen=True)
class WhoopConfig:
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> "WhoopConfig":
        required = ("WHOOP_CLIENT_ID", "WHOOP_CLIENT_SECRET")
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise ConfigError(f"missing environment variable(s): {', '.join(missing)}")
        return cls(
            client_id=os.environ["WHOOP_CLIENT_ID"],
            client_secret=os.environ["WHOOP_CLIENT_SECRET"],
            redirect_uri=os.environ.get("WHOOP_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        )


def new_state() -> str:
    return secrets.token_urlsafe(16)


def authorize_url(config: WhoopConfig, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": SCOPES,
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def parse_redirect(pasted_url: str, expected_state: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(pasted_url.strip()).query)
    code = query.get("code", [None])[0]
    state = query.get("state", [None])[0]
    if not code:
        raise AuthError("the pasted URL has no `code` parameter")
    if state != expected_state:
        raise AuthError("`state` does not match this login attempt; run `auth` again")
    return code


def _tokens_from(response: dict) -> Tokens:
    try:
        return Tokens(
            access_token=response["access_token"],
            refresh_token=response["refresh_token"],
            expires_at=time.time() + float(response["expires_in"]),
        )
    except KeyError as e:
        raise AuthError(
            f"token response is missing {e}; was the `offline` scope granted?"
        ) from None


def exchange_code(config: WhoopConfig, code: str) -> Tokens:
    try:
        response = http.post_form(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "redirect_uri": config.redirect_uri,
            },
        )
    except http.HttpError as e:
        raise AuthError(f"WHOOP rejected the code: {e.body or e}") from None
    return _tokens_from(response)


def refresh(config: WhoopConfig, tokens: Tokens) -> Tokens:
    try:
        response = http.post_form(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "refresh_token": tokens.refresh_token,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "scope": "offline",
            },
        )
    except http.HttpError as e:
        raise AuthError(f"WHOOP rejected the refresh token ({e.body or e}). {RELOGIN}") from None
    return _tokens_from(response)


def _usable(tokens: Tokens | None, rejected: str | None) -> bool:
    if tokens is None or tokens.access_token == rejected:
        return False
    return tokens.expires_at - time.time() > REFRESH_MARGIN_SECONDS


def valid_access_token(
    store: TokenStore, config: WhoopConfig, rejected: str | None = None
) -> str:
    """Return an access token, refreshing (under the lock) if needed.

    `rejected` is a token the API just refused; passing it forces a refresh
    unless someone else has already replaced it.
    """
    tokens = store.load(PROVIDER)
    if tokens is None:
        raise AuthError(RELOGIN)
    if _usable(tokens, rejected):
        return tokens.access_token
    with store.refresh_lock():
        tokens = store.load(PROVIDER)  # re-read: a concurrent refresh may have landed
        if _usable(tokens, rejected):
            return tokens.access_token
        new_tokens = refresh(config, tokens)
        store.save(PROVIDER, new_tokens)
        return new_tokens.access_token
```

- [ ] **Step 6: Run to verify they pass**

Run: `uv run pytest -q`
Expected: `29 passed`.

- [ ] **Step 7: Commit**

```bash
git add src/fitness_app/env.py src/fitness_app/whoop/auth.py tests/test_env.py tests/test_whoop_auth.py
git commit -m "feat(whoop): add OAuth flow with locked, persisted token refresh

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `whoop/client.py` — endpoints, date window, pagination, 401 retry

**Files:**
- Create: `src/fitness_app/whoop/client.py`
- Test: `tests/test_whoop_client.py`

**Interfaces:**
- Consumes: `http.get_json`, `http.HttpError`, `auth.valid_access_token(store, config, rejected=None)`, `TokenStore`, `WhoopConfig`.
- Produces:
  - `API_BASE = "https://api.prod.whoop.com/developer/v2"`, `PAGE_SIZE = 25`, `MAX_PAGES = 20`.
  - `class WhoopClient(store: TokenStore, config: WhoopConfig)` with
    `get_recovery(days: int = 7) -> list[dict]`, `get_sleep(days=7)`, `get_workouts(days=7)`, `get_cycles(days=7)`, `get_profile() -> dict`, `get_body_measurements() -> dict`. Lists are raw WHOOP records, newest first as WHOOP returns them.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_whoop_client.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fitness_app.whoop.client'`.

- [ ] **Step 3: Implement**

```python
# src/fitness_app/whoop/client.py
"""Typed access to the WHOOP v2 API. Knows nothing about MCP.

Handles exactly one error itself: a 401 triggers one refresh and one
retry. Everything else propagates as `http.HttpError`.
"""

from datetime import datetime, timedelta, timezone

from fitness_app import http
from fitness_app.tokenstore import TokenStore
from fitness_app.whoop import auth
from fitness_app.whoop.auth import WhoopConfig

API_BASE = "https://api.prod.whoop.com/developer/v2"
PAGE_SIZE = 25
MAX_PAGES = 20


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


class WhoopClient:
    def __init__(self, store: TokenStore, config: WhoopConfig):
        self.store = store
        self.config = config

    @staticmethod
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        token = auth.valid_access_token(self.store, self.config)
        try:
            return http.get_json(API_BASE + path, params, self._headers(token))
        except http.HttpError as e:
            if e.status != 401:
                raise
        token = auth.valid_access_token(self.store, self.config, rejected=token)
        return http.get_json(API_BASE + path, params, self._headers(token))

    def _paginated(self, path: str, days: int) -> list[dict]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        params: dict = {"start": _iso(start), "end": _iso(end), "limit": PAGE_SIZE}
        records: list[dict] = []
        for _ in range(MAX_PAGES):
            page = self._get(path, params)
            records.extend(page.get("records", []))
            next_token = page.get("next_token")
            if not next_token:
                break
            params = {**params, "nextToken": next_token}
        return records

    def get_recovery(self, days: int = 7) -> list[dict]:
        return self._paginated("/recovery", days)

    def get_sleep(self, days: int = 7) -> list[dict]:
        return self._paginated("/activity/sleep", days)

    def get_workouts(self, days: int = 7) -> list[dict]:
        return self._paginated("/activity/workout", days)

    def get_cycles(self, days: int = 7) -> list[dict]:
        return self._paginated("/cycle", days)

    def get_profile(self) -> dict:
        return self._get("/user/profile/basic")

    def get_body_measurements(self) -> dict:
        return self._get("/user/measurement/body")
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest -q`
Expected: `36 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/fitness_app/whoop/client.py tests/test_whoop_client.py
git commit -m "feat(whoop): add API client with pagination and single 401 retry

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: `whoop/server.py` — trimmed tools and the MCP adapter

**Files:**
- Create: `src/fitness_app/whoop/server.py`
- Test: `tests/test_whoop_server.py`

**Interfaces:**
- Consumes: `WhoopClient`, `TokenStore`, `WhoopConfig.from_env`, `auth.AuthError`.
- Produces:
  - Pure functions `trim_recovery(record) -> dict`, `trim_sleep(record) -> dict`, `trim_workout(record) -> dict`, `trim_cycle(record) -> dict`.
  - Tool functions (plain callables, registered by `create_server`): `get_recovery(days: int = 7) -> list[dict]`, `get_sleep(days: int = 7)`, `get_workouts(days: int = 7)`, `get_cycles(days: int = 7)`, `get_profile() -> dict`, `get_body_measurements() -> dict`.
  - `_client() -> WhoopClient` — the single place a client is built; tests replace it.
  - `create_server() -> FastMCP`.

Tools are plain functions so tests call them directly; `create_server()` registers them with `FastMCP`. The `mcp` SDK converts any exception raised inside a tool into an error result whose text is the exception message — that is how `AuthError`'s re-login instruction reaches Claude.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_whoop_server.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fitness_app.whoop.server'`.

- [ ] **Step 3: Implement**

```python
# src/fitness_app/whoop/server.py
"""MCP adapter: six tools, one per client method, each trimmed to what a
coach needs. Knows nothing about OAuth.

Tools are plain functions registered in `create_server()` so tests can
call them directly. Exceptions raised here become MCP error results with
the exception message as text — that is how the re-login instruction in
`AuthError` reaches the model.
"""

from mcp.server.fastmcp import FastMCP

from fitness_app.tokenstore import TokenStore
from fitness_app.whoop.auth import WhoopConfig
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


def create_server() -> FastMCP:
    mcp = FastMCP("whoop")
    for tool in TOOLS:
        mcp.tool()(tool)
    return mcp
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest -q`
Expected: `47 passed`. If `test_create_server_registers_six_tools` fails on `_tool_manager`, the installed `mcp` version exposes tools differently: replace the body with `names = {t.name for t in __import__("asyncio").run(mcp.list_tools())}` and keep the assertion.

- [ ] **Step 5: Commit**

```bash
git add src/fitness_app/whoop/server.py tests/test_whoop_server.py
git commit -m "feat(whoop): expose six trimmed tools through FastMCP

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: `whoop/__main__.py` — the CLI

**Files:**
- Create: `src/fitness_app/whoop/__main__.py`
- Test: `tests/test_whoop_cli.py`

**Interfaces:**
- Consumes: `env.load_dotenv`, `WhoopConfig.from_env`, `ConfigError`, `AuthError`, `new_state`, `authorize_url`, `parse_redirect`, `exchange_code`, `TokenStore`, `WhoopClient`, `create_server`.
- Produces: `main(argv: list[str] | None = None) -> int` and `cmd_auth(config, store, input_fn=input, print_fn=print) -> int`, `cmd_status(config, store, print_fn=print) -> int`, `cmd_serve(config, store) -> int`. Exit codes: 0 ok, 1 auth/API failure, 2 configuration missing.

`.mcp.json` runs this module with no argument, so `serve` is the default.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_whoop_cli.py -q`
Expected: FAIL with `ImportError` / `ModuleNotFoundError` for `fitness_app.whoop.__main__`.

- [ ] **Step 3: Implement**

```python
# src/fitness_app/whoop/__main__.py
"""CLI: `auth` (once), `status` (config, token, one live call), `serve`
(default; what .mcp.json runs).

`serve` speaks MCP over stdout, so logging is configured to stderr and
nothing in the serve path may print.
"""

import argparse
import logging
import sys
import time

from fitness_app.env import load_dotenv
from fitness_app.tokenstore import TokenStore
from fitness_app.whoop import auth
from fitness_app.whoop.client import WhoopClient


def cmd_auth(config: auth.WhoopConfig, store: TokenStore, input_fn=input, print_fn=print) -> int:
    state = auth.new_state()
    print_fn("1. Open this URL in your browser and approve access:\n")
    print_fn(auth.authorize_url(config, state) + "\n")
    print_fn("2. Your browser will land on the redirect URI. A 'connection refused'")
    print_fn("   page is expected — nothing is listening there on purpose.")
    pasted = input_fn("3. Paste the full URL from the address bar here: ")
    code = auth.parse_redirect(pasted, state)
    tokens = auth.exchange_code(config, code)
    store.save(auth.PROVIDER, tokens)
    print_fn("Authorised. Tokens saved to", store.path)
    return 0


def cmd_status(config: auth.WhoopConfig, store: TokenStore, print_fn=print) -> int:
    print_fn("config: client id and secret present; redirect uri", config.redirect_uri)
    tokens = store.load(auth.PROVIDER)
    if tokens is None:
        print_fn("token: none.", auth.RELOGIN)
        return 1
    minutes = (tokens.expires_at - time.time()) / 60
    if minutes > 0:
        print_fn(f"token: present, access token expires in {minutes:.0f} min")
    else:
        print_fn("token: present, access token expired (will refresh on next call)")
    profile = WhoopClient(store, config).get_profile()
    print_fn("live call: OK — profile for", profile.get("first_name"), profile.get("last_name"))
    return 0


def cmd_serve(config: auth.WhoopConfig, store: TokenStore) -> int:
    from fitness_app.whoop.server import create_server

    create_server().run()  # stdio transport
    return 0


COMMANDS = {"auth": cmd_auth, "status": cmd_status, "serve": cmd_serve}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m fitness_app.whoop")
    parser.add_argument("command", nargs="?", default="serve", choices=sorted(COMMANDS))
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s"
    )
    load_dotenv()
    try:
        config = auth.WhoopConfig.from_env()
    except auth.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    store = TokenStore()
    try:
        return COMMANDS[args.command](config, store)
    except auth.AuthError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest -q`
Expected: `52 passed`.

- [ ] **Step 5: Confirm the server actually starts**

Run:
```bash
WHOOP_CLIENT_ID=x WHOOP_CLIENT_SECRET=y timeout 3 uv run python -m fitness_app.whoop; echo "exit $?"
```
Expected: no traceback; process waits on stdin and `timeout` kills it (exit 124). A traceback here means the `mcp` import or `FastMCP.run()` is wrong — fix before committing.

- [ ] **Step 6: Commit**

```bash
git add src/fitness_app/whoop/__main__.py tests/test_whoop_cli.py
git commit -m "feat(whoop): add auth/status/serve CLI

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Converse A — live login, smoke test, first conversation

**Files:**
- Modify: `README.md` (add "Running it" section)
- Verify: `.mcp.json`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above, plus `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` present in the Codespace environment (owner adds them as Codespaces secrets **before** this task; if `env | grep WHOOP_` shows nothing, stop and ask the owner to add them and rebuild the Codespace).

- [ ] **Step 1: Confirm secrets are present**

Run: `env | grep -c '^WHOOP_CLIENT_'`
Expected: `2`.

- [ ] **Step 2: Log in once (owner at the keyboard)**

Run: `uv run python -m fitness_app.whoop auth`
The owner opens the printed URL, approves, and pastes back the URL their browser lands on. Expected: `Authorised. Tokens saved to .data/tokens.sqlite`. Confirm `.data/` is gitignored: `git status --porcelain | grep -c .data` prints `0`.

- [ ] **Step 3: Smoke test**

Run: `uv run python -m fitness_app.whoop status`
Expected: config line, `token: present, access token expires in N min`, `live call: OK — profile for <name>`.

- [ ] **Step 4: Verify `.mcp.json` is what Claude Code will read**

Run: `cat .mcp.json`
Expected:
```json
{
  "mcpServers": {
    "whoop": {
      "command": "uv",
      "args": ["run", "python", "-m", "fitness_app.whoop"]
    }
  }
}
```

- [ ] **Step 5: Start Claude Code and check the server is connected**

Run `claude` in the repo root. Inside it, run `/mcp`. Expected: `whoop` listed as connected with six tools. If it shows an error, run `uv run python -m fitness_app.whoop` by hand and read stderr.

- [ ] **Step 6: Converse**

Ask: *"How recovered am I this week, and how did I sleep?"* Expected: Claude calls `get_recovery` and `get_sleep` and answers with real numbers. Then ask: *"What did I train in the last 7 days?"* Expected: `get_workouts` is called.

- [ ] **Step 7: Document how to run it**

Append to `README.md`:

```markdown
## Running it

1. Register a WHOOP developer app — see `docs/whoop-app-setup.md`.
2. Put `WHOOP_CLIENT_ID` and `WHOOP_CLIENT_SECRET` in the environment
   (GitHub → Settings → Codespaces → Secrets, or a local `.env`).
3. `uv sync`
4. `uv run python -m fitness_app.whoop auth` — once; follow the prompts.
5. `uv run python -m fitness_app.whoop status` — confirms config, token and one live call.
6. `claude` — Claude Code reads `.mcp.json`, starts the server, and `CLAUDE.md` makes it a coach.

Tests: `uv run pytest -q`. They run offline; nothing in `tests/` touches the network.
```

- [ ] **Step 8: Commit**

```bash
git add README.md
git commit -m "docs: add running instructions after first live conversation

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: Strava spike and decision record

**Files:**
- Create: `docs/decisions/0001-strava-integration.md`
- Possibly modify: `.mcp.json` (only if outcome B below)

**Interfaces:**
- Produces: a decision that the next milestone's spec argues from. No code beyond a config line.

Timebox: one hour of wall-clock time. Whatever is known at the end gets written down.

- [ ] **Step 1: Try the connector route**

Inside `claude`, run `/mcp`. Look for a Strava entry provided by the claude.ai account (connectors enabled on the account may appear here). If present, ask *"what did I run in the last 7 days?"* and note whether a Strava tool is called.

- [ ] **Step 2: Try the remote-MCP-by-URL route**

Search Strava's developer documentation and the MCP registry for an official hosted MCP endpoint (an `https://` URL that speaks MCP). If one exists, add it to `.mcp.json`:

```json
"strava": { "type": "http", "url": "<the documented url>" }
```

Restart `claude`, run `/mcp`, complete the OAuth prompt in the browser, and repeat the question from Step 1.

- [ ] **Step 3: Write the decision record**

```markdown
# 0001 — How Strava is reached

Date: <today>
Status: accepted

## Context

Strava activities are the second data source. The design preferred an
existing MCP over a hand-written client, if Claude Code in the Codespace
can reach one. This was unknown and timeboxed to one hour.

## What was tried

- Connector route (claude.ai account connectors visible in `/mcp`): <worked / not visible / errored: ...>
- Remote MCP by URL in `.mcp.json`: <url found: ... / no documented endpoint> — <result>

## Decision

<One of:>
A. Strava via the account connector. Nothing in the repo; documented here.
B. Strava via remote MCP in `.mcp.json` (committed). OAuth done once in the browser.
C. Neither reachable. Strava becomes a second client under `fitness_app/strava/`
   sharing `http.py` and `tokenstore.py` (provider = "strava"), specified in
   the next milestone.

## Consequences

<Two or three lines: what Converse A can and cannot answer about running
right now; what the next spec must include.>
```

- [ ] **Step 4: Commit**

```bash
git add docs/decisions/0001-strava-integration.md .mcp.json
git commit -m "docs: record Strava integration decision after spike

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done when

- `uv run pytest -q` is green.
- `uv run python -m fitness_app.whoop status` makes one successful live call.
- In `claude`, "how recovered am I this week and what did I run?" is answered from real Whoop data, and Strava is either answered too or explained in `docs/decisions/0001-strava-integration.md`.
- `git log --oneline` reads as one feature per commit.
