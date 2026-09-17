# fitness-coach

A personal training coach for one runner, built toward the 2027 New York
City Marathon. It reads recovery and sleep from WHOOP and activities from
Strava, will hold a versioned training plan, and adapts that plan through
conversation — always proposing a change and waiting for a yes.

It is also a portfolio project: the repository is meant to be read. The
design lives in `docs/specs/`, the step-by-step build in `docs/plans/`,
and each non-obvious choice in `docs/decisions/`.

## Status

Milestone 1 — a WHOOP MCP server built from scratch, and a first
conversation with real data through Claude Code. See
`docs/specs/2026-09-17-whoop-mcp-converse-a-design.md`.

## Layout

```
src/fitness_app/
├── http.py          # urllib helpers; logs path and status only
├── tokenstore.py    # SQLite, one row per provider, atomic save
└── whoop/           # OAuth, API client, MCP server, CLI
docs/                # specs, plans, decisions, setup notes
tests/               # offline; the network is always faked
```

## Principles

- Secrets come from the environment. `.env` was ignored in the first commit.
- Standard library first. `mcp` is the only runtime dependency.
- Every threshold and guardrail carries its provenance.
- The plan is a versioned object in a database, never inferred from chat.
