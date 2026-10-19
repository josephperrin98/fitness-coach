# Build plan

Each step ends with something that runs, is tested, and is pushed. No step is "write a document".

## Done (this seed)
Plan object, rules with provenance, validator, propose/confirm store, day-of gate, CLI, 46 tests, CI.

## Step 1 -- coach-core MCP server
Expose the store and validator to an agent over MCP (Python MCP SDK, stdio).
Tools: `get_plan`, `validate_plan`, `propose_change`, `confirm_change` (human-initiated path only), `check_gate`.
Acceptance: an MCP client can propose a plan with a soft violation, see the finding, and be refused a confirm until the rule is acknowledged.
Decision to record: the agent is given `propose_change` but `confirm_change` sits behind a separate entry point.

## Step 2 -- plan generator
Given goal, race date and weekly availability, produce a candidate 4+1 plan, then run it through the validator. Generation is deterministic; the LLM only explains and adjusts.
Acceptance: generated plans for a half and a marathon validate with no hard findings.

## Step 3 -- skills
`start-here`, `intake`, `weekly-checkin` as SKILL.md files that call the MCP tools. Ship with a README setup prompt.
Acceptance: from a fresh Claude project, a person can upload the skills and get a validated plan.

## Step 4 -- read-only data
Strava via its own MCP at runtime, never stored. Whoop via the community MCP as reference. A thin baseline log of the user's own test results (performance numbers only).

## Step 5 -- thin dashboard
Plan versus actual, current week type, and the pending-change queue. Not an analytics product.

## Open decisions
- Strava API policy: whether a user-confirmed value derived from Strava counts as stored derived data. Ask Strava support before persisting anything.
- Taper and acute:chronic load rules need numbers and sources before they enter `rules.yaml`.
- Physio confirmation of the day-of gate ladder.
