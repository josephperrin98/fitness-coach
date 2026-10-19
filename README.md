# fitness-coach

A training-plan **validator** and a **propose-then-confirm plan store**, built as the foundation of an AI coach for a marathon build.

The idea in one sentence: an AI agent may *propose* changes to a training plan, but nothing it proposes takes effect until it has passed deterministic, sourced rules and a human has confirmed it.

## Why this exists

Generic plan generators and recovery apps share three gaps:

1. They say how recovered you are, not what to do about it given where you are in a training block.
2. Their progression logic ignores concurrent sport (here: football and strength work).
3. They know nothing about an individual's injury history.

The valuable part is therefore the **adaptation layer**: judgment about the next step, constrained by rules the user can read, question and change. This repo is that layer. Data aggregation (Strava, Whoop) is deliberately not the product.

## How it works

```
 agent / user
      |  propose(plan)
      v
 +-------------+      +-----------------+
 |  validator  |<-----|  rules.yaml     |  every rule: tier, status, provenance
 +-------------+      +-----------------+
      |
      |-- hard violation --> status: rejected   (kept for audit, can never be confirmed)
      |-- soft violation --> status: pending    (needs explicit acknowledgement by rule id)
      '-- clean ----------> status: pending
                                  |  confirm(version, acknowledged={...})   <- human only
                                  v
                          status: confirmed   (previous plan -> superseded)
```

Three rule tiers, by who is trusted to decide:

| Tier | Where it lives | Behaviour |
|---|---|---|
| Hard | code + `rules.yaml` | the plan is rejected |
| Soft | code + `rules.yaml` | the plan can be confirmed only if the user acknowledges that rule |
| Judgment | LLM, in the check-in skill | advises, never blocks |

A separate **day-of gate** (`coach/gates.py`) checks a self-rated 0-10 score for a flagged body area on the morning of a session, with a stricter threshold for all-out efforts.

## Rules carry their provenance

Each rule in [`rules/rules.yaml`](rules/rules.yaml) records where its number came from: `literature`, `clinical`, `professional` or `personal_choice`, plus a note. The loader refuses a rule with no provenance. This makes disagreement debuggable: the recovery-week cap is 60% of the block peak because that was a deliberate personal choice at the conservative end of the usual range, and the file says so. The weekly-increase caps cite the fact that trials (Buist 2008, Nielsen 2014) found no significant injury difference, so they are labelled monitoring thresholds, not proven safe limits.

## Run it

```bash
pip install -e ".[dev,mcp]"
pytest -q
python -m coach validate examples/plan.example.yaml
python -m coach gate 2 --effort maximal     # -> MODIFY: all-out efforts need a lower score
python -m coach demo-data                   # synthetic data for the dashboard's demo mode
python -m http.server -d dashboard          # then open http://localhost:8000
```

The example plan and the demo data are synthetic. A real plan goes in `plan.local.yaml`, which is gitignored:

```bash
python -m coach propose plan.local.yaml --rationale "first block"
python -m coach confirm 1                   # only a human can do this; the agent has no confirm tool
```

## The daily loop

```
 morning: "check in"  ->  Claude (skills/daily-check-in)
                            |  get_today, check_gate, record_check_in      <- coach-core (this repo, MCP)
                            |  recovery, sleep, workouts                   <- whoop-mcp (MCP)
                            |  yesterday's activities                      <- Strava connector
                            v
                      decision for TODAY only: go / modify / rest
                      (code refuses anything that adds load; that is a plan change for the weekly review)
```

- **Check-in** decides today. **Weekly review** changes the plan, through propose and a human confirm.
- **Adherence score** per session: short costs 1 point per 1% under target, over costs 0.5 points per 1% (falling short is worse), moved within the week costs 10, missed scores 0. Within 5% is labelled done. Rates live in `rules.yaml` with their provenance.
- **Execution score**: share of minutes inside the planned heart-rate ceiling, from Whoop zones joined to the Strava run by start time.

## The dashboard

`dashboard/index.html` is one HTML page. Opened as an Artifact in the Claude desktop app, it calls the Strava connector and the local whoop and coach-core servers through the viewer's own connections, and coach-core computes everything it draws. Anywhere else (GitHub Pages, a local server) it draws `dashboard/demo-data.json`, a synthetic athlete run through the same scoring code.

Views: a calendar of past and future sessions (planned vs done, score, check-in, morning recovery), weekly adherence, execution and km, and what each kind of day costs in next-morning HRV against your own median.

**Strava's API terms forbid feeding its data to AI models**, so the model only sees Strava through Strava's own connector, and nothing from Strava is ever written to disk here. The page hands Strava rows to coach-core on the same machine for one computation.

## Evals

```bash
python -m evals.checkin_evals
```

Six check-in scenarios (green, modify, stop, the stricter test-day gate, a request to add load, no consent) run through `claude -p` against a throwaway database and are graded on what was **stored**, not on what the model said. The grader has its own unit tests.

## What is built, and what is not

| Area | State |
|---|---|
| Plan object (weeks, sessions, types, life-event overlay) | built |
| Validator: recovery, restart, loading streak, weekly load, run frequency, 5-run windows, football by week type, hard sessions | built |
| Propose / confirm / supersede lifecycle with audit trail (SQLite) | built |
| Day-of caution gate | built |
| Adherence and execution scores | built |
| Daily check-in store, today-only and easier-only | built |
| coach-core MCP server (no confirm tool) and CLI | built |
| Daily check-in skill and its evals | built, 6/6 on first run |
| Dashboard with demo mode | built (v0) |
| Weekly review skill, plan generation, intake for other users | not built |
| Bedtime, time-of-day and efficiency views | not built |
| Taper volume rule, acute:chronic load flag | not built |

Roadmap: [`docs/build-plan.md`](docs/build-plan.md). This version's design and decisions D17-D23: [`docs/specs/2026-10-19-v0-design.md`](docs/specs/2026-10-19-v0-design.md).

## Decisions worth defending

- **Rules as data, not code.** Thresholds sit in YAML with provenance, so changing one is a reviewable diff, not a code change.
- **Propose-then-confirm, enforced in the store.** The agent's only write path is `propose()`. This is a structural limit on autonomy, not a prompt instruction.
- **Hard rejections are stored, not dropped.** The audit trail shows what the agent tried to do.
- **SQLite over Postgres.** Runs anywhere with no setup; the schema is plain enough to move when there is something to deploy. A simpler option chosen deliberately.
- **No health detail in the repo.** Rules refer to a generic "caution area"; what it is lives in private config. Nothing from Strava's API is persisted (its API policy forbids it); performance numbers the user records themselves are fine.

## Limits to be honest about

- Several rule thresholds are `proposed`, not `decided`, and the day-of gate ladder awaits professional confirmation.
- The rules are conventions and personal choices more than proven science, which is why each one says so.
- Single user so far. A multi-user intake flow is planned, not built.
- The evals are one run of six scenarios: a smoke test, not a measure of reliability.
- The dashboard's live mode only works for the artifact's owner, in the Claude desktop app with whoop-mcp and coach-core running.
