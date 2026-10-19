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
| Judgment | LLM (not in this repo yet) | advises, never blocks |

A separate **day-of gate** (`coach/gates.py`) checks a self-rated 0-10 score for a flagged body area on the morning of a session, with a stricter threshold for all-out efforts.

## Rules carry their provenance

Each rule in [`rules/rules.yaml`](rules/rules.yaml) records where its number came from: `literature`, `clinical`, `professional` or `personal_choice`, plus a note. The loader refuses a rule with no provenance. This makes disagreement debuggable: the recovery-week cap is 60% of the block peak because that was a deliberate personal choice at the conservative end of the usual range, and the file says so. The weekly-increase caps cite the fact that trials (Buist 2008, Nielsen 2014) found no significant injury difference, so they are labelled monitoring thresholds, not proven safe limits.

## Run it

```bash
pip install -e ".[dev]"
pytest -q
python -m coach validate examples/plan.example.yaml
python -m coach gate 2 --effort maximal     # -> MODIFY: all-out efforts need a lower score
```

The example plan uses synthetic numbers. A real plan goes in `plan.local.yaml`, which is gitignored.

## What is built, and what is not

| Area | State |
|---|---|
| Plan object (weeks, types, life-event overlay) | built |
| Validator: recovery, restart, loading streak, weekly load, run frequency, 5-run windows, football by week type, hard sessions | built, 46 tests |
| Propose / confirm / supersede lifecycle with audit trail (SQLite) | built |
| Day-of caution gate | built |
| Taper volume rule, acute:chronic load flag | not built |
| Plan generation from goal and race date | not built |
| MCP server exposing the coach tools to an agent | not built |
| Skills (onboarding, weekly check-in), Strava / Whoop read-only connectors | not built |
| Dashboard | not built |

Roadmap and open decisions: [`docs/build-plan.md`](docs/build-plan.md).

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
