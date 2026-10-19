"""Command line for the human side of the loop.

    python -m coach validate examples/plan.example.yaml
    python -m coach propose plan.local.yaml --rationale "first block"
    python -m coach pending
    python -m coach confirm 3 --ack R-REC-3
    python -m coach serve            # the MCP server Claude Desktop starts

confirm exists only here, never in the MCP server: a human types it.
"""
from __future__ import annotations

import argparse
import sys

from .gates import check_caution_gate
from .store import ConfirmationError
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

    pr = sub.add_parser("propose", help="propose a plan file (validated at once)")
    pr.add_argument("plan")
    pr.add_argument("--rationale", default="")

    sub.add_parser("pending", help="list proposals waiting for confirmation")

    c = sub.add_parser("confirm", help="confirm a pending proposal (human only)")
    c.add_argument("version", type=int)
    c.add_argument("--ack", action="append", default=[], help="acknowledge a soft rule by id")

    sub.add_parser("serve", help="run the coach-core MCP server on stdio")

    args = parser.parse_args(argv)

    if args.cmd in ("propose", "pending", "confirm"):
        from .service import Coach   # opens the database, so only for these commands
        coach = Coach()
        if args.cmd == "propose":
            with open(args.plan, encoding="utf-8") as fh:
                result = coach.propose(fh.read(), args.rationale, author="user")
            print(f"version {result['version']}: {result['status']}")
            for f in result["findings"]:
                print(f"  {f}")
            return 1 if result["status"] == "rejected" else 0
        if args.cmd == "pending":
            for p in coach.pending():
                print(f"{p['version']}  by {p['author']}  {p['created_at']}  {p['rationale']}")
            return 0
        try:
            coach.confirm(args.version, set(args.ack))
        except ConfirmationError as e:
            print(f"not confirmed: {e}")
            return 1
        print(f"version {args.version} confirmed")
        return 0

    if args.cmd == "serve":
        from .mcp_server import main as serve
        serve()
        return 0

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
