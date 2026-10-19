"""Day-of gate for a flagged caution area (a joint with history).

Deliberately separate from the plan validator: a plan is checked in advance,
a gate is checked on the morning, against how the body actually feels.
No health detail lives here -- the user names the caution area in private config.
"""
from __future__ import annotations

from dataclasses import dataclass

from .rules import RuleSet, load_rules


@dataclass(frozen=True)
class GateDecision:
    decision: str   # go | modify | stop
    reason: str


def check_caution_gate(score: int, effort: str = "run", rules: RuleSet | None = None) -> GateDecision:
    """score is the user's own 0-10 rating; effort is 'run' or 'maximal'."""
    if not 0 <= score <= 10:
        raise ValueError("score must be between 0 and 10")
    if effort not in ("run", "maximal"):
        raise ValueError("effort must be 'run' or 'maximal'")

    g = (rules or load_rules()).gates["caution_area"]

    if score > g["run_modify_max"]:
        return GateDecision("stop", f"score {score} is above {g['run_modify_max']}: no running today")
    if score > g["run_go_max"]:
        return GateDecision("modify", f"score {score}: shorten, flatten or slow the session")
    if effort == "maximal" and score > g["maximal_effort_max"]:
        return GateDecision(
            "modify",
            f"score {score} is fine for easy running but all-out efforts need "
            f"{g['maximal_effort_max']} or lower: swap for a steady run",
        )
    return GateDecision("go", f"score {score}: clear for planned session")
