# CONTEXT.local.md

Strategic context for the fitness coach app. Read before starting work.
Committed on purpose: nothing here is secret, and it makes the repo legible to a stranger.

## What this project is

A training coach for one user (me), built around a 2027 NYC Marathon build roughly 13–14 months out. It aggregates Strava and Whoop data, generates and adapts a training plan, and talks to me about it.

It is also a portfolio artifact for deployment engineer / AI deployment strategist interviews. That means the repo itself is a deliverable: README, architecture notes, and commit history should be legible to a stranger evaluating my judgment.

## What it is not

Not a Strava replacement. Not an analytics dashboard. The performance-view problem is solved by tools I already pay for; this system's value is the planning and adaptation layer on top.

## Decisions already made — do not relitigate without telling me

- **Web app, ideally a PWA.** Not native mobile.
- **Single agent with tools**, reached through multiple entry points (chat, weekly Monday session, monthly block review), each with its own system prompt. Multi-agent only for the research subsystem, where parallel isolated context genuinely helps.
- **Propose-then-confirm.** The agent never silently applies a plan change. There is a pending-change state.
- **The plan is a structured, versioned object** in the database — never inferred from conversation history.
- **Plan generation is in scope.** Strava's V3 API is retrospective only (activities, segments, athletes, clubs, routes, gear, streams, uploads) — there is no planned-workout endpoint and no public Runna API, so there is no external baseline plan to adapt.
- **Build the Whoop MCP from scratch.** No official one exists. Community implementations exist and are fine to consult when stuck, but the point is that I built it.
- **Strava** is reached via its existing MCP.
- **Secrets come from the environment**, never from a tracked file — write it that way from the first commit, even locally.

## Constraints

- Everything lives on my personal GitHub. Nothing persists on a work machine. Development happens in a Codespace.
- Public repo, so secret hygiene is not theoretical. `.gitignore` gets `.env` before any credential exists.
- I am a confident user of AI coding tools but not a career engineer. Explain non-obvious choices briefly rather than assuming; I'd rather understand the structure than have it quietly handled.

## Domain specifics that shape the code

- Running is primary. Cycling, occasional swimming, and 1–2 weekly gym sessions are a supporting layer the plan must account for, not ignore. Multi-sport load balancing is a first-class concern — it's where the commercial tools measurably fail.
- There is a personal-constraints layer: flagged caution areas where any meaningful increase in impact loading requires explicit confirmation. This is a hard requirement, not a nice-to-have.
- Every guardrail and threshold carries provenance — where the number came from (literature, clinical guidance, professional calibration, my own judgment).
- Cadence is three nested horizons: macro (the marathon), meso (monthly blocks), micro (the week, with a Monday check-in including a short subjective review).

## Still open

- Target marathon time and the threshold sequence. Blocks the plan schema — not the integration work.
- Professional calibration of the personal-constraint thresholds.
- Host and database choice. Postgres leaning, decided when there's something to deploy.

## Working conventions

- Timebox OAuth and token refresh. If it isn't working after a day, read a working implementation rather than persisting. It's plumbing; it should be boring.
- Prefer the simplest thing that works, and say out loud when a simpler option was chosen over a more sophisticated one — those decisions are part of what the repo is demonstrating.

---

## Session log

### 2026-09-17 — kickoff

**Changed**
- Public repo created: https://github.com/josephperrin98/fitness-coach. Commits under perrin.joseph@hotmail.fr (per-repo config).
- Design spec approved and committed: `docs/specs/2026-09-17-whoop-mcp-converse-a-design.md`.
- Implementation plan committed: `docs/plans/2026-09-17-whoop-mcp-converse-a.md` — 9 tasks, test-first, written for a cold Claude Code session in the Codespace.
- Skeleton committed: devcontainer, `.mcp.json`, `CLAUDE.md` (coach persona), README, PRIVACY.md (filled), pyproject, empty package. No source yet.
- Agreed milestone sequence: Whoop MCP → Strava → Converse A (Claude Code in Codespace) → Converse B (own agent) → self-reports (per-session ankle/soreness; weekly survey incl. coach evaluation; upcoming-week context e.g. travel/party) → plan schema + constraints layer → plan generation → weekly/monthly entry points → PWA → research subsystem.
- Decision: Claude Desktop cannot reach a Codespace MCP over stdio, so Converse A runs Claude Code inside the Codespace (option A).
- Decision: approach 1 — Python, `mcp` as the only runtime dependency, `pytest` dev-only, `uv` + lockfile, SQLite token store, paste-the-redirect-URL login.

**Next**
1. Register the WHOOP app (developer.whoop.com) — privacy URL `https://github.com/josephperrin98/fitness-coach/blob/main/PRIVACY.md`, redirect URI `http://localhost:8765/callback`, six read scopes.
2. Add `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` as Codespaces secrets with repo access to fitness-coach.
3. Create the Codespace, open a terminal, `claude`, and execute `docs/plans/2026-09-17-whoop-mcp-converse-a.md` task by task.
4. Task 8 = Converse A. Task 9 = one-hour Strava spike → `docs/decisions/0001-strava-integration.md`.

**Still open** (unchanged): target marathon time; professional calibration of ankle thresholds; host/database.
