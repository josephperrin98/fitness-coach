# Context for Claude Code

This repo is two things at once: a training tool the owner really uses, and a portfolio artifact for AI-deployment interviews. Code, commit messages and docs should be legible to a stranger judging engineering judgment.

## Read first
`README.md` (design), `docs/build-plan.md` (what to build next), `rules/rules.yaml` (the rules and where they came from).

## Commands
```bash
pip install -e ".[dev]"
pytest -q
python -m coach validate examples/plan.example.yaml
```

## Decisions already made -- do not relitigate without saying so
- The plan is a structured, versioned object, never inferred from chat history.
- The agent proposes; a human confirms. Do not add a code path where the agent can confirm.
- Rules live in `rules/rules.yaml` with provenance. A rule without a known source is refused at load time. Do not hard-code thresholds in Python.
- Hard rules reject; soft rules need acknowledgement by rule id.
- Simplest thing that works (SQLite, stdio MCP). Say out loud when a simpler option was chosen over a sophisticated one.

## Privacy and policy constraints
- Public repo. No health detail, no real training plan, no secrets: `.env`, `*.local.yaml`, `*.local.md` and `*.db` are gitignored. Keep it that way.
- Nothing returned by the Strava API may be stored or fed to a model outside Strava's own MCP.
- Commit with the owner's personal identity only. Do not bypass any hook that blocks a commit.

## Working style
- Explain non-obvious choices briefly; the owner is not a career engineer and wants to understand the structure.
- Every step ends with tests passing and a push. Add a test with each rule change.
- Metric units only.
