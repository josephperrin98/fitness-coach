"""Versioned plan store with a propose-then-confirm lifecycle.

    propose() -> validator -> hard violation?  -> status 'rejected' (kept for audit)
                           -> otherwise        -> status 'pending'
    confirm() -> every soft violation must be acknowledged by rule id
              -> status 'confirmed'; the previous confirmed plan becomes 'superseded'

The agent can only ever call propose(). Nothing it does changes the plan
that is in force until a human calls confirm(). That is the autonomy boundary.

SQLite keeps this runnable anywhere with no setup. The schema is plain enough
to move to Postgres when there is something to deploy.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .plan import Plan, plan_from_dict, plan_to_dict
from .rules import RuleSet, load_rules
from .validator import Violation, validate

SCHEMA = """
CREATE TABLE IF NOT EXISTS plan_versions (
    version      INTEGER PRIMARY KEY AUTOINCREMENT,
    status       TEXT NOT NULL CHECK (status IN ('pending','confirmed','superseded','rejected')),
    author       TEXT NOT NULL,
    rationale    TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    decided_at   TEXT,
    payload      TEXT NOT NULL,      -- the plan, as JSON
    violations   TEXT NOT NULL,      -- validator findings at proposal time, as JSON
    acknowledged TEXT NOT NULL DEFAULT '[]'
);
"""


class ConfirmationError(Exception):
    """Raised when a plan cannot be confirmed as it stands."""


@dataclass(frozen=True)
class Proposal:
    version: int
    status: str
    violations: tuple[Violation, ...]

    @property
    def hard(self) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.tier == "hard")

    @property
    def soft(self) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.tier == "soft")


class PlanStore:
    def __init__(self, path: str = ":memory:", rules: RuleSet | None = None) -> None:
        self.rules = rules or load_rules()
        # The MCP server runs tools on worker threads; calls arrive one at a time from a
        # single user, so sharing one connection across threads is safe here.
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # -- writes ---------------------------------------------------------------
    def propose(self, plan: Plan, author: str = "agent", rationale: str = "") -> Proposal:
        violations = validate(plan, self.rules)
        status = "rejected" if any(v.tier == "hard" for v in violations) else "pending"
        cur = self.db.execute(
            "INSERT INTO plan_versions (status, author, rationale, created_at, payload, violations)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (status, author, rationale, _now(), json.dumps(plan_to_dict(plan)),
             json.dumps([_violation_to_dict(v) for v in violations])),
        )
        self.db.commit()
        return Proposal(version=cur.lastrowid, status=status, violations=tuple(violations))

    def confirm(self, version: int, acknowledged: set[str] | frozenset[str] = frozenset()) -> None:
        row = self._row(version)
        if row["status"] == "rejected":
            raise ConfirmationError(f"version {version} broke a hard rule and cannot be confirmed")
        if row["status"] != "pending":
            raise ConfirmationError(f"version {version} is {row['status']}, not pending")

        soft_rules = {v["rule"] for v in json.loads(row["violations"]) if v["tier"] == "soft"}
        missing = sorted(soft_rules - set(acknowledged))
        if missing:
            raise ConfirmationError(f"soft rules need explicit acknowledgement: {', '.join(missing)}")

        with self.db:
            self.db.execute("UPDATE plan_versions SET status='superseded', decided_at=? WHERE status='confirmed'",
                            (_now(),))
            self.db.execute("UPDATE plan_versions SET status='confirmed', decided_at=?, acknowledged=? WHERE version=?",
                            (_now(), json.dumps(sorted(acknowledged)), version))

    def withdraw(self, version: int) -> None:
        """Discard a pending proposal without confirming it."""
        row = self._row(version)
        if row["status"] != "pending":
            raise ConfirmationError(f"version {version} is {row['status']}, not pending")
        self.db.execute("UPDATE plan_versions SET status='rejected', decided_at=? WHERE version=?",
                        (_now(), version))
        self.db.commit()

    # -- reads ----------------------------------------------------------------
    def current(self) -> Plan | None:
        row = self.db.execute("SELECT payload FROM plan_versions WHERE status='confirmed'").fetchone()
        return plan_from_dict(json.loads(row["payload"])) if row else None

    def history(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT version, status, author, rationale, created_at, decided_at FROM plan_versions ORDER BY version"
        ).fetchall()
        return [dict(r) for r in rows]

    def _row(self, version: int) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM plan_versions WHERE version=?", (version,)).fetchone()
        if row is None:
            raise ConfirmationError(f"no such version: {version}")
        return row


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _violation_to_dict(v: Violation) -> dict:
    return {"rule": v.rule, "tier": v.tier, "status": v.status, "source": v.source,
            "week": v.week.isoformat() if v.week else None, "message": v.message}
