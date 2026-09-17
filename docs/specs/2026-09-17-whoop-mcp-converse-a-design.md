# Design: Whoop MCP and Converse A

Date: 2026-09-17
Status: approved for planning
Scope: milestone 1 of the fitness coach — steps 0–3 of the agreed sequence

## 1. Purpose

Build a Whoop MCP server from scratch, wire Strava alongside it, and reach
**Converse A**: talking to real training data through Claude Code, with no
application code of our own beyond the MCP server.

**Definition of done.** In the Codespace, the owner types `claude` and asks
*"how recovered am I this week and what did I run?"* The answer cites real
Whoop numbers, and either real Strava numbers or a decision record
(`docs/decisions/0001-strava-integration.md`) explaining why Strava is
deferred to its own client.

## 2. Context and constraints

- The project is a personal marathon coach (2027 NYC) and a portfolio
  artifact. The repo is public; README, commits and docs are deliverables.
- Development happens in a GitHub Codespace. Nothing persists on the
  owner's work laptop beyond an empty folder.
- Claude Desktop cannot start an MCP server that lives in a Codespace
  (stdio transport needs both processes on one machine), so Converse A
  uses **Claude Code inside the Codespace**, configured by `.mcp.json`.
- Secrets come from the environment only: GitHub Codespaces secrets in
  the cloud, `.env` locally. `.env` was gitignored in the first commit.
- Strava is reached through its existing remote MCP if Claude Code in
  the Codespace can use it; otherwise it becomes a second client sharing
  the Whoop plumbing. Deciding that is a one-hour spike inside this
  milestone.

## 3. Decisions

| Decision | Choice | Rejected | Why |
|---|---|---|---|
| Language | Python 3.12 | TypeScript | Owner's conventions (service layer, stdlib); Converse B's agent reads naturally in Python |
| Dependencies | `mcp` only at runtime; `pytest` dev-only | `httpx`, `pydantic`, `respx` | Every dependency is something that can break and must be explained; stdlib `urllib` and `sqlite3` suffice |
| Packaging | `uv` with committed `uv.lock` | pip + requirements.txt | Reproducible installs are a deployment signal |
| Layout | one repo, `src/` layout, Whoop as a subpackage | separate `whoop-mcp` repo | One lockfile, one CI; split later if anyone else installs it |
| Structure | `client` (talks to Whoop) and `server` (thin MCP adapter) | one module doing both | Converse B imports the client directly with no MCP in between |
| Token storage | SQLite, one row per provider | JSON file | A transaction gives atomic persist and serialised refresh for free |
| First login | print URL, owner pastes redirect URL back | local callback server | No ports, no tunnel; Codespace localhost is not the browser's localhost |
| Retries | 401 → refresh once → retry once; nothing else | backoff loop | Add when a real 429 is observed (YAGNI) |
| Tests | pytest + monkeypatch, fake HTTP | recorded real fixtures | Field names from docs; `status` command catches drift |

## 4. Architecture

```
fitness_app/
├── .devcontainer/devcontainer.json   # Codespace recipe: Python 3.12, uv, Claude Code
├── .mcp.json                         # how Claude Code starts the Whoop server
├── CLAUDE.md                         # coach persona = Converse A system prompt
├── PRIVACY.md                        # required by WHOOP registration
├── README.md
├── pyproject.toml, uv.lock
├── .gitignore, .env.example
├── docs/
│   ├── whoop-app-setup.md
│   ├── specs/                        # this document
│   ├── plans/                        # implementation plans
│   └── decisions/                    # ADRs, e.g. 0001-strava-integration.md
├── src/fitness_app/
│   ├── http.py                       # get_json(), post_form() over urllib
│   ├── tokenstore.py                 # sqlite3, one row per provider, refresh lock
│   └── whoop/
│       ├── __main__.py               # CLI: auth | status | serve (default)
│       ├── auth.py                   # authorize URL, code exchange, refresh
│       ├── client.py                 # WhoopClient: six endpoints, pagination
│       └── server.py                 # FastMCP adapter: six tools, 1:1 with client
└── tests/
```

`http.py` and `tokenstore.py` sit outside `whoop/` because nothing in
them is Whoop-specific; the store is keyed by provider name so a Strava
client can reuse both without a refactor. That is the only
forward-looking concession in this milestone.

## 5. Components

Each module has one reason to change.

**`http.py`** — `get_json(url, headers) -> dict`, `post_form(url, data, headers) -> dict`.
Raises `HttpError(status, body)` on non-2xx. Logs method, path, status —
never headers or bodies. Knows nothing about auth.

**`tokenstore.py`** — `TokenStore(path)` with `load(provider) -> Tokens | None`
and `save(provider, tokens)`. `Tokens` is a dataclass:
`access_token`, `refresh_token`, `expires_at` (absolute UTC timestamp).
`save` is one transaction. Exposes a `refresh_lock()` context manager
(a `threading.Lock`; SQLite `timeout=5` covers a second process).
Path defaults to `.data/tokens.sqlite`, overridable by `FITNESS_DATA_DIR`.

**`whoop/auth.py`** — reads `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`,
`WHOOP_REDIRECT_URI` from the environment.
- `authorize_url(state) -> str` with scopes
  `read:recovery read:sleep read:cycles read:workout read:profile read:body_measurement offline`.
- `exchange_code(code) -> Tokens`, `refresh(tokens) -> Tokens`.
- `valid_access_token(store) -> str`: return the stored token if it
  expires more than 60 s from now; otherwise take the refresh lock,
  re-read the row (another refresh may have landed), refresh if still
  stale, save the new pair, return the new access token.
- Raises `AuthError` with a re-login instruction when no row exists or
  the refresh token is rejected.

**`whoop/client.py`** — `WhoopClient(store)` with
`get_recovery(days)`, `get_sleep(days)`, `get_workouts(days)`,
`get_cycles(days)`, `get_profile()`, `get_body_measurements()`.
Builds `start`/`end` from `days`, follows `next_token` up to 20 pages,
returns lists of raw records. On 401: refresh once, retry once.
Knows nothing about MCP.

**`whoop/server.py`** — `FastMCP("whoop")` exposing six tools with the
same names and arguments as the client. Each trims records to the fields
a coach uses (e.g. recovery: date, score, HRV, resting HR, sleep
performance) and returns JSON. `AuthError` and `HttpError` propagate as
tool errors with their messages intact. Knows nothing about OAuth.

**`whoop/__main__.py`** — subcommands:
- `auth`: print the authorize URL, prompt for the pasted redirect URL,
  verify `state`, exchange, save. Run once.
- `status`: report config presence, token presence and expiry (never the
  token), then one live call to `/v2/user/profile/basic`.
- `serve` (default): validate config, start the stdio server.

## 6. Data flow

**First login (once).** `auth` → prints URL → owner approves at WHOOP →
browser lands on `http://localhost:8765/callback?code=…&state=…` (nothing
listening; "connection refused" is expected) → owner pastes the URL →
`state` checked → code exchanged with client secret → row saved.

**A tool call (every time).** Claude Code starts `serve` per `.mcp.json`
→ Claude picks a tool → `server` → `client` → `auth.valid_access_token`
(refresh under lock if needed, new pair saved atomically) → `http` GET
with pagination → `server` trims → JSON back to Claude.

Refresh tokens rotate on every use and the old one dies immediately; a
lost write means manual re-login. The lock plus the transaction exist
for exactly that.

## 7. Error handling

Every failure names the next action; nothing printed ever contains a token.

| Where | Condition | Behaviour |
|---|---|---|
| startup | missing `WHOOP_CLIENT_ID`/`_SECRET` | `serve` exits naming the variable |
| any tool | no token row | tool error: "Not authorised. Run `uv run python -m fitness_app.whoop auth`." Server stays up so the message reaches Claude |
| auth | pasted URL lacks `code` or `state` mismatch | abort, nothing saved |
| auth | token endpoint rejects code | show WHOOP's error verbatim, nothing saved |
| refresh | refresh token rejected | `AuthError` with re-login instruction; stale row left in place |
| http | 401 | refresh once, retry once |
| http | 429 / 5xx / other | `HttpError(status, path)` propagates; no retry |
| http | network error | propagates with endpoint name |
| client | pagination beyond 20 pages | stop; guards against an infinite loop |
| store | SQLite locked | wait up to 5 s (`timeout=5`) |

## 8. Testing

All tests run offline in under a second, faking `http.py` with
`monkeypatch`. `http.py` itself is not unit-tested; the `status` command
is its live check.

- `tokenstore`: save/load round-trip; failed save leaves old row intact.
- `auth`: authorize URL carries all seven scopes and `state`; `state`
  mismatch aborts; refresh persists the new pair; rejected refresh
  raises `AuthError`.
- `client`: follows `next_token` across pages; stops at the cap;
  401 triggers exactly one refresh and one retry.
- `server`: each tool trims to expected fields; missing token yields the
  instruction message, not a crash.

Manual smoke test before Converse A: `uv run python -m fitness_app.whoop status`.

## 9. Bootstrap sequence and roles

| # | Where | Who | What |
|---|---|---|---|
| 1 | work Mac, this session | Claude | skeleton, docs, spec, plan; commits under `perrin.joseph@hotmail.fr` |
| 2 | GitHub | Claude (`gh`, authorised by owner) | create public repo `josephperrin98/fitness-coach`, push |
| 3 | work Mac | Claude | delete folder contents, keep the empty folder |
| 4 | developer.whoop.com | owner | register app per `docs/whoop-app-setup.md`; privacy URL `https://github.com/josephperrin98/fitness-coach/blob/main/PRIVACY.md`; redirect URI `http://localhost:8765/callback` |
| 5 | GitHub settings | owner | add `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET` as Codespaces secrets |
| 6 | Codespace | owner + a fresh Claude Code session | execute `docs/plans/` test-first, one commit per task |
| 7 | Codespace | owner | `auth`, `status`, `claude`, ask the question |
| 8 | Codespace | Claude | Strava spike, one hour, outcome in `docs/decisions/0001-strava-integration.md` |

The plan is written for a cold session with none of this conversation.

## 10. Configuration

| Variable | Set where | Purpose |
|---|---|---|
| `WHOOP_CLIENT_ID` | Codespaces secret / `.env` | app identity |
| `WHOOP_CLIENT_SECRET` | Codespaces secret / `.env` | app secret, server-side only |
| `WHOOP_REDIRECT_URI` | `.env.example` default `http://localhost:8765/callback` | must match the registered URI |
| `FITNESS_DATA_DIR` | optional, default `.data/` | where `tokens.sqlite` lives |

`.mcp.json` runs `uv run python -m fitness_app.whoop` from the repo root.

## 11. Converse A persona (`CLAUDE.md`)

Deliberately short: a marathon coach for a runner who also cycles, swims
occasionally and lifts twice a week; consult the whoop tools before any
claim about recovery, sleep or strain; never propose an increase in
impact load without asking about the previously injured ankle. The full
constraints layer with provenance is a later milestone.

## 12. Out of scope for this milestone

Any database beyond the token store; caching activities; the plan
schema; self-reports; the agent loop (Converse B); the PWA; the research
subsystem; Strava beyond the spike.
