"""Command line: python -m coach validate examples/plan.example.yaml"""
from __future__ import annotations

import argparse
import sys

from .gates import check_caution_gate
from .plan import load_plan
from .rules import load_rules
from .validator import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coach", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check a plan file against the rules")
    v.add_argument("plan")
    v.add_argument("--rules", default=None, help="path to an alternative rules.yaml")

    g = sub.add_parser("gate", help="day-of check for a flagged caution area")
    g.add_argument("score", type=int, help="your 0-10 rating today")
    g.add_argument("--effort", choices=["run", "maximal"], default="run")

    args = parser.parse_args(argv)

    if args.cmd == "validate":
        rules = load_rules(args.rules) if args.rules else load_rules()
        findings = validate(load_plan(args.plan), rules)
        for f in findings:
            print(f)
        hard = sum(1 for f in findings if f.tier == "hard")
        soft = len(findings) - hard
        print(f"\n{hard} hard, {soft} soft")
        return 1 if hard else 0

    decision = check_caution_gate(args.score, args.effort)
    print(f"{decision.decision.upper()}: {decision.reason}")
    return 0 if decision.decision == "go" else 2


if __name__ == "__main__":
    sys.exit(main())
