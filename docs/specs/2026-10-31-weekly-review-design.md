# v1 design: weekly review, paces, drift, dashboard pages

Agreed 31 Oct 2026. Builds on `2026-10-19-v0-design.md` (D17-D23 stay in force).
All numbers below are examples. Real values live in `plan.local.yaml` and the
database, both gitignored.

## Goal

One planning decision a week, made with real numbers: how the last week went,
whether the athlete is drifting from the objective, and paced sessions for the next
two weeks. The model drafts; code checks; the human confirms.

## Decisions

| # | Decision |
|---|---|
| D24 | Three horizons. **Route**: weekly totals to the next race, plus a planned VDOT line. **Schedule**: sessions on days for this week and next. **Day**: the safety gate. Sessions are never placed more than two weeks ahead. |
| D25 | The route is drafted by the model and checked by the existing validator; no plan generator in code. It is proposed and confirmed like any plan. |
| D26 | One planning process: the **Monday review**. It places sessions for this week and next from the athlete's stated availability (mornings, evenings, weekend) and sends one proposal. It changes the route only when drift persists, an objective changes, or the athlete asks. No separate monthly review. |
| D27 | The daily check-in shrinks to the safety gate, asked only on test or maximal days, plus read-only questions ("what's on tomorrow?"). A day changes only when the athlete asks: easier is recorded after a yes (D20), more load becomes a proposal. |
| D28 | A scheduled task prepares the review on Mondays at 09:00 local time. It runs unattended, so it is read-only: it summarises and notifies, and never proposes. It runs on the athlete's Mac, because whoop-mcp and coach-core are local. |
| D29 | Paces come from one fitness number, VDOT (Daniels and Gilbert formulas, `literature`). A session stores its intent (`pace: threshold`, `structure: 3 x 10 min`); seconds per km are computed from that week's VDOT. Easy and long runs also carry a heart-rate ceiling. |
| D30 | The planned VDOT line rises from the last checkpoint to the target VDOT, reached two weeks before the race, and stays flat in recovery weeks. The VDOT used for paces is capped at **last checkpoint + 1.0** (`personal_choice`): the plan may aim high, evidence limits how far it runs ahead. |
| D31 | Checkpoints every 4 weeks, at the end of a recovery week, alternating a 6-minute test and a 5 km time trial. A result is shown to the athlete and stored only after they confirm it, as their own input (D21: Strava data is never stored). |
| D32 | Volume drift: run km done / route km over the last 4 weeks. 90-110 % on track, 75-90 % watch, under 75 % behind, over 110 % ahead. Behind or ahead on **two Mondays in a row** opens the route branch. Fitness drift: checkpoint VDOT more than 1.0 below the line opens it. Thresholds are `personal_choice`. |
| D33 | Execution per session: whether the run matched its prescription (structure and pace band), computed live from Strava laps, never stored. Most reliable when the athlete presses lap at each block. |
| D34 | The dashboard shows only what Strava and Whoop do not: plan against reality, the VDOT line, drift, recovery beside training. Session depth stays in Strava. |

## Pieces

1. `coach/fitness.py`: VDOT from a result, pace for each session kind, the planned line, the cap.
2. `coach/drift.py`: volume and fitness drift, the two-Monday rule.
3. `coach/plan.py`: plan gains a target time; a session gains `pace` and `structure`.
4. `coach/store.py`: a checkpoints table (date, kind, distance, seconds, VDOT).
5. coach-core tools: `get_paces`, `drift`, `record_checkpoint`; `get_today` returns paces. Still no confirm tool.
6. `skills/weekly-review/SKILL.md`, with a route branch. `daily-check-in` is trimmed per D27.
7. Scheduled task for the Monday 09:00 prep (D28).
8. `rules/rules.yaml`: entries for D30, D32 and the weekly tick (below), each with provenance.
9. Evals: the review places two weeks inside the stated availability; never raises totals above the route without the branch; opens the branch only after two Mondays; never confirms.

## Dashboard

Light theme by default. Simple shapes, few numbers per screen. One icon per
activity kind (weights, bike, kite, ball, shoe), drawn inline.

| Page | Question | Shows |
|---|---|---|
| **Today** (opens first) | How am I, what was last, what is next? | This morning's recovery and how the athlete feels; the last session and the next one with its pace; three week blocks (last, this, next), each run coloured by that morning's recovery (Whoop bands: green 67 % and up, yellow 34-66 %, red under 34 %). A back arrow and zoom out for more weeks. |
| **Program** | Am I doing the runs I should, and what comes next? | This week's and next week's sessions: structure, pace, heart-rate ceiling, and a short explanation of what each session is for. Past sessions show their execution against the prescription (D33), for example "3 x 10 min at 4:40: 3 of 3 blocks in band". Then the route as weekly totals. |
| **Progress** | Where did I start, where am I, where should I be? | The VDOT line with checkpoint dots; weekly volume planned against done; one tick or cross per week **with the adherence score** (tick at 80 or above, `personal_choice`; weeks before the plan show actual km in grey, no tick); pace adherence %; a fitness curve; bests (1 km, 5 km, 10 km, 15 km, half) for the last 4 weeks against the 4 before. |

The fitness curve uses the standard load model on Strava's relative effort for every
activity: fitness = 42-day weighted average, fatigue = 7-day, form = fitness minus
fatigue. Strava's own chart is not reachable through its connector, so this is an
equivalent built from the same input; its numbers may differ, and it needs about
three months of history before it settles. Easy runs are not plotted as VDOT: they
are not maximal efforts.

The per-sport HRV view leaves the main pages.

## Build order

1. `fitness.py` and paces on sessions.
2. The route to the next race, proposed and confirmed.
3. The weekly-review skill.
4. Drift.
5. The Monday 09:00 prep task.
6. Evals.
7. Dashboard pages.

Until step 3 exists, the next two weeks are drafted by hand through the existing
propose and confirm flow, with paces written in each session's note.

## Out of v1

Triggering on each new Strava activity (needs a public webhook endpoint), a plan
generator in code, sessions placed beyond two weeks, other runners.
