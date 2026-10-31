"""Load rules from rules/rules.yaml, keeping provenance attached to every rule."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "rules.yaml"
SOURCES = ("literature", "clinical", "professional", "personal_choice")


@dataclass(frozen=True)
class Rule:
    id: str
    summary: str
    tier: str                  # hard | soft
    status: str                # decided | proposed
    params: dict[str, Any]
    source: str                # provenance category
    note: str = ""


@dataclass(frozen=True)
class RuleSet:
    version: str
    rules: dict[str, Rule]
    gates: dict[str, Any] = field(default_factory=dict)
    scoring: dict[str, Any] = field(default_factory=dict)
    paces: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, rule_id: str) -> Rule:
        return self.rules[rule_id]


def load_rules(path: str | Path = DEFAULT_RULES_PATH) -> RuleSet:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    rules: dict[str, Rule] = {}
    for rule_id, body in raw["rules"].items():
        prov = body.get("provenance") or {}
        source = prov.get("source")
        if source not in SOURCES:
            # A rule without a known origin is a rule nobody can debate.
            raise ValueError(f"{rule_id}: provenance.source must be one of {SOURCES}, got {source!r}")
        if body["tier"] not in ("hard", "soft"):
            raise ValueError(f"{rule_id}: tier must be hard or soft")
        rules[rule_id] = Rule(
            id=rule_id,
            summary=body["summary"],
            tier=body["tier"],
            status=body["status"],
            params=body.get("params", {}),
            source=source,
            note=" ".join(str(prov.get("note", "")).split()),
        )
    scoring = raw.get("scoring", {})
    if scoring and (scoring.get("provenance") or {}).get("source") not in SOURCES:
        raise ValueError(f"scoring: provenance.source must be one of {SOURCES}")
    paces = raw.get("paces", {})
    for part in ("intensity", "progression"):
        if paces and (paces.get(part, {}).get("provenance") or {}).get("source") not in SOURCES:
            raise ValueError(f"paces.{part}: provenance.source must be one of {SOURCES}")
    return RuleSet(version=str(raw["version"]), rules=rules, gates=raw.get("gates", {}),
                   scoring=scoring, paces=paces)
