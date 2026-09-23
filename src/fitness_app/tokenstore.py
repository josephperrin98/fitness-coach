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
