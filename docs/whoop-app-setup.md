# WHOOP developer app — setup checklist

Verified against WHOOP's developer docs, September 2026.

## Before you start

You need a WHOOP account — the one your membership is on. The developer dashboard authenticates through `id.whoop.com` with those same credentials. There is no separate developer signup and no documented approval queue, so this should be self-serve rather than a wait.

## Steps

1. Go to **developer.whoop.com** and sign in with your WHOOP account.
2. **Create a team.** First-time users are prompted for this before any app can exist. Any name is fine — it's an organisational wrapper, not something users see.
3. **Create an app.** You'll be asked for:
   - **Name** — e.g. `fitness_app`
   - **Scopes** — at least one is required. See below.
   - **Redirect URI** — at least one is required. See below.
4. **Submit.** You get a **client ID** and a **client secret**.

You can create up to 5 apps on an account; more requires requesting a limit increase.

## Scopes to request

Request all of these. Adding a scope later means re-authorising, so it's cheaper to take them now:

| Scope | What it gives you |
|---|---|
| `read:recovery` | Recovery score, HRV, resting heart rate |
| `read:cycles` | Daily strain, average HR per physiological cycle |
| `read:workout` | Workout strain and average HR |
| `read:sleep` | Sleep performance %, duration per stage |
| `read:profile` | Name and email |
| `read:body_measurement` | Height, weight, max HR |
| **`offline`** | **Refresh tokens** |

**Correction: `offline` is not a dashboard toggle.** It isn't selected when you register the app — it's passed in the `scope` parameter of your authorization URL at runtime, alongside the read scopes. In the dashboard, select the six read scopes only. In code, the authorize request carries:

`scope=read:recovery read:sleep read:cycles read:workout read:profile read:body_measurement offline`

**It is still the one that matters most.** Without it WHOOP issues no refresh token at all, which means your app stops working the moment the first access token expires and can only be revived by you logging in again by hand. A scheduled Monday replanning job cannot survive that. If you take one thing from this page, take this.

## Do the repo first

The registration form requires a privacy policy URL, which means you need a URL that resolves before you can finish registering. Create the GitHub repo first, add `PRIVACY.md`, push it, and use its GitHub URL here. This reverses the order given earlier.

## Redirect URI

This is where WHOOP sends the user back after they approve access. The documented examples are `https://...` URLs and custom schemes like `whoop://...`; the docs don't confirm whether `http://localhost` is accepted. Try registering a localhost callback first, since that's what you need while developing. If it's rejected, you can add the production URL later and use a tunnel for local testing — worth knowing before you're mid-flow rather than discovering it then.

You can register more than one, so add the localhost one now and the real host URL when you have it.

## The secret

Save the client secret into `.env` the moment it appears — these are typically shown once. It is server-side only: never logged, never in client code, never committed. `.gitignore` should already list `.env` before you get here.

## Two traps specific to WHOOP's token flow

Both are documented behaviour, and both are how people lock themselves out:

**Refresh tokens rotate.** Every refresh response contains a *new* refresh token, and using a refresh token invalidates the existing access token. If your code fetches a new token pair but fails to persist the new refresh token, you are locked out and back to manual re-authorisation. Write the persistence step before you write anything else, and make it atomic.

**Concurrent refreshes fail.** Two processes refreshing at the same moment will break each other. With a scheduled job plus an interactive app, this is a real possibility — serialise refreshes through a single path rather than letting each caller refresh on demand.

## API shape (v2)

For your first milestone — last seven days of recovery:

- `GET /v2/recovery` — all recoveries, paginated
- `GET /v2/cycle` — cycles, paginated
- `GET /v2/activity/sleep` — sleep sessions, paginated
- `GET /v2/activity/workout` — workouts, paginated
- `GET /v2/user/profile/basic`

OAuth endpoints:
- Authorize: `https://api.prod.whoop.com/oauth/oauth2/auth`
- Token: `https://api.prod.whoop.com/oauth/oauth2/token`

## If you need support

I could not find a documented developer support email address — so rather than guess one, the entry points are the developer site itself (developer.whoop.com) and WHOOP's general support portal, which carries an article on the developer platform. The app-limit increase is the one request the docs explicitly mention as something you ask for, so there is a channel for it; find it from the dashboard rather than from a guessed address.

## Where the secret goes in a Codespace

GitHub → **Settings → Codespaces → Secrets → New secret**. Create
`WHOOP_CLIENT_ID` and `WHOOP_CLIENT_SECRET`, and under *Repository access*
tick `fitness-coach`. They are injected as environment variables into every
Codespace for that repo. If a Codespace was already running, rebuild it
(Command Palette → "Codespaces: Rebuild Container") for the new secrets to
appear.
