# Dashboard: Today and Program pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The dashboard opens on a light Today page (how you are, last and next session, three week blocks with runs coloured by recovery and icons per activity) with a Program page beside it (this week's and next week's sessions with pace, heart-rate ceiling and purpose, then the route as weekly totals), and a Progress tab that says what it is waiting for.

**Architecture:** `coach/views.py` computes everything the pages show (D23: the page stays a renderer): each session's purpose, the check-in's feel, the last and next session, and the route. `dashboard/index.html` becomes three pages behind tabs, routed by a bare `#today` / `#program` / `#progress` hash. Pieces that need later build steps (execution against the prescription D33, VDOT dots, drift) render as a short panel saying what they wait for.

**Tech Stack:** Python 3 standard library, pytest; one static HTML page with inline CSS, inline JS and an inline SVG icon sprite. No libraries.

**Spec:** `docs/specs/2026-10-31-weekly-review-design.md` (Dashboard section, D33, D34).

## Global Constraints

- No new dependencies, in Python or in the page (no CDN scripts). Fonts stay on Google Fonts as today.
- Logic in `coach/` (service layer); the page draws what `dashboard_data` returns and computes nothing that matters.
- Light theme by default: no `prefers-color-scheme` block. Dark only on an explicit `:root[data-theme="dark"]`. Every colour is a token on `:root`; `body` keeps an explicit background.
- Works at 400 px wide with no horizontal page scroll; only the calendar grid may scroll inside its own container.
- Every string from data is inserted with `esc()` or `textContent`.
- The repo is public: tests use textbook values, the demo stays synthetic (`python -m coach demo-data`).
- Strava data is never stored (D21). Metric units only.
- Conventional Commits, one task per commit, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run the whole suite before the first task and after the last: `.venv/bin/python -m pytest -q` (150 pass at the start).
- Page checks: `python3 -m http.server 8765 -d dashboard`, open `http://localhost:8765/index.html` (demo mode, today = 2026-12-09, a Wednesday with a quality session).

---

### Task 1: Dashboard data for Today and Program

**Files:**
- Modify: `coach/views.py`
- Modify: `dashboard/demo-data.json` (regenerated, never hand-edited)
- Test: `tests/test_sources_and_views.py`, `tests/test_service_and_server.py`, `tests/test_demo.py`

**Interfaces:**
- Consumes: `views.add_pace_bands(out, bands_for)` (exists; mutates each `days[].planned[]` dict in place).
- Produces, in the `dashboard()` result:
  - `days[].planned[].purpose: str | None` — one sentence, keyed by the session's `pace` if set, else its `kind`.
  - `days[].checkin.feel: int | None`.
  - `last_session: {"date": str, "kind": str, "minutes": float, "km": float, "recovery": float | None} | None` — the latest activity on or before today that is not `walk` or `other`; `recovery` is that morning's.
  - `next_session: {"date": str, "session": <the same dict object as in days[].planned>} | None` — the first planned session on or after today whose score status is `upcoming`. Same object, so `add_pace_bands` fills its `pace_band` too.
  - `route: [{"start": str, "type": str, "km": float}]` — every plan week from this week's Monday to the race.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sources_and_views.py`:

```python
def test_dashboard_gives_today_and_program_what_they_draw():
    store = CheckInStore(":memory:")
    store.record(CheckIn(day=date(2026, 10, 21), decision="go", reason="fine", feel=6), PLAN)
    acts = merge(actuals_from_strava(STRAVA), actuals_from_whoop(WHOOP))
    recs = [{"date": "2026-10-21", "recovery": 72, "hrv": 61.0}]
    out = dashboard(PLAN, store, acts, recs, today=date(2026, 10, 21), weeks_back=1, weeks_ahead=0)

    assert out["last_session"] == {"date": "2026-10-21", "kind": "strength", "minutes": 40.0,
                                   "km": 0.0, "recovery": 72}
    assert out["next_session"]["date"] == "2026-10-23"
    assert out["next_session"]["session"]["kind"] == "easy"
    assert out["next_session"]["session"]["purpose"].startswith("Easy")
    assert out["route"] == [{"start": "2026-10-19", "type": "foundation", "km": 15}]
    wed = next(d for d in out["days"] if d["date"] == "2026-10-21")
    assert wed["checkin"]["feel"] == 6
    tue = next(d for d in out["days"] if d["date"] == "2026-10-20")
    assert tue["planned"][0]["purpose"].startswith("Team sport")


def test_walks_are_not_a_last_session():
    walk = [{"sport_type": "Walk", "start_local": "2026-10-22T12:00:00",
             "summary": {"distance": 3000, "moving_time": 1800}}]
    acts = actuals_from_strava(STRAVA + walk)
    out = dashboard(PLAN, CheckInStore(":memory:"), acts, [], today=date(2026, 10, 22),
                    weeks_back=1, weeks_ahead=0)
    assert out["last_session"]["kind"] == "football"
```

Append to `tests/test_service_and_server.py`:

```python
def test_next_session_carries_its_pace_band(tmp_path):
    c = Coach(str(tmp_path / "paced.db"))
    c.confirm(c.propose(PACED, "seed", author="user")["version"], set())
    c.record_checkpoint(Checkpoint(day=date(2026, 10, 19), kind="5k", distance_m=5000, seconds=1200))
    nxt = c.dashboard(MON, "[]", "[]", "[]")["next_session"]
    assert nxt["date"] == "2026-10-20"
    assert nxt["session"]["pace_band"] == c.paces(date(2026, 10, 20))["paces"]["threshold"]
```

Append to `tests/test_demo.py`:

```python
def test_demo_has_a_last_and_next_session_and_a_route():
    d = demo_dashboard()
    assert d["last_session"]["date"] <= DEMO_TODAY.isoformat() <= d["next_session"]["date"]
    assert d["route"][0]["start"] == "2026-12-07"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_sources_and_views.py tests/test_service_and_server.py tests/test_demo.py`
Expected: 4 FAIL with `KeyError: 'last_session'` / `'next_session'` / `'route'`.

- [ ] **Step 3: Implement in `coach/views.py`**

Below `MIN_SAMPLES`, add:

```python
# One line per session on the Program page, keyed by pace intent, else by kind.
PURPOSE = {
    "easy": "Easy, conversational running: builds the aerobic base with little fatigue.",
    "long": "The week's longest run, kept easy: builds endurance for the race distance.",
    "threshold": "Comfortably hard: raises the pace you can hold for about an hour.",
    "interval": "Hard repeats with recoveries: raises your maximal aerobic capacity.",
    "race": "At goal race pace: practises the rhythm of race day.",
    "quality": "The week's harder run: the structure says what to do.",
    "test": "A maximal test: measures fitness so paces stay honest.",
    "football": "Team sport: counts as hard training, so keep the next day easy.",
    "strength": "Strength work: sturdier legs and more economical running.",
}
NOT_TRAINING = ("walk", "other")   # shown in the day detail, never as the last session
```

In `dashboard()`, change the check-in dict to add `feel`:

```python
            "checkin": {"decision": c.decision, "reason": c.reason, "feel": c.feel,
                        "adjusted_target": c.adjusted_target} if c else None,
```

Replace the `return {...}` of `dashboard()` with:

```python
    return {
        "today": today.isoformat(),
        "goal": {"kind": plan.goal, "race_date": plan.race_date.isoformat(),
                 "days_to_race": (plan.race_date - today).days} if plan else None,
        "days": days,
        "weeks": weeks,
        "last_session": _last_session(actuals, rec_by_day, today),
        "next_session": _next_session(days, today),
        "route": [{"start": w.start.isoformat(), "type": w.type, "km": w.km}
                  for w in (plan.weeks if plan else ()) if w.start >= monday],
        "activity_cost": activity_cost(actuals, recoveries, plan),
    }


def _last_session(actuals: list[Actual], rec_by_day: dict, today: date) -> dict[str, Any] | None:
    past = [a for a in actuals if a.day <= today and a.kind not in NOT_TRAINING]
    if not past:
        return None
    a = max(past, key=lambda x: (x.day, x.start or datetime.min))
    rec = rec_by_day.get(a.day)
    return {"date": a.day.isoformat(), "kind": a.kind, "minutes": a.minutes, "km": a.km,
            "recovery": rec["recovery"] if rec else None}


def _next_session(days: list[dict], today: date) -> dict[str, Any] | None:
    # Returns the day's own session dict, not a copy, so add_pace_bands fills it too.
    for d in days:
        if d["date"] < today.isoformat():
            continue
        for s in d["planned"]:
            if s.get("score", {"status": "upcoming"})["status"] == "upcoming":
                return {"date": d["date"], "session": s}
    return None
```

Change the `datetime` import line to `from datetime import date, datetime, timedelta`.

In `_session()`, add the purpose to `out`:

```python
    out = {"kind": x.kind, "target": x.target, "unit": x.unit, "zone_max": x.zone_max, "note": x.note,
           "pace": x.pace, "structure": x.structure, "purpose": PURPOSE.get(x.pace or x.kind)}
```

Note: sessions past the scored window have no `score` key; `_next_session` treats a missing score as upcoming.

- [ ] **Step 4: Regenerate the demo and run the suite**

Run: `.venv/bin/python -m coach demo-data && .venv/bin/python -m pytest -q`
Expected: `wrote dashboard/demo-data.json`, then 154 passed.

- [ ] **Step 5: Commit**

```bash
git add coach/views.py dashboard/demo-data.json tests/test_sources_and_views.py tests/test_service_and_server.py tests/test_demo.py
git commit -m "feat(views): last and next session, route and session purpose for the dashboard

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Page shell: light theme, tabs, icons, Progress placeholder

**Files:**
- Modify: `dashboard/index.html`

**Interfaces:**
- Consumes: nothing new from Task 1 yet.
- Produces (used by Tasks 3 and 4): element ids `page-today`, `page-program`, `page-progress`, `today`, `cal`, `legend`, `detail`, `earlier`, `later`, `zoom`, `program`, `route`; JS helpers `icon(kind) -> string` (an inline `<svg class="ico">`), `ICON` map, `showPage(name)`; CSS classes `.ico`, `.wait`, `.tabs`.

- [ ] **Step 1: Light theme by default**

Delete the whole `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }` block. Keep the bare `:root` block and the `:root[data-theme="dark"]` block unchanged.

- [ ] **Step 2: Remove what leaves the main pages**

Delete these CSS blocks: everything under `/* weeks */` (`.weeks`, `.wk`, `.bars`, `.bar`, `.wk small`) and everything under `/* activity cost */` (`.cost`, `.crow`, `.track`, `.fill`, `.crow .v`). In the `@media (max-width: 520px)` block delete the two `.crow` rules.

In the markup, delete the `<section>` holding `<h2>Weeks</h2>` and the `<section>` holding `<h2>What each day costs you</h2>`.

In the script, delete `renderWeeks` and `renderCost`, and in `render()` replace
`renderToday(d); renderWeeks(d); renderCalendar(d); renderCost(d.activity_cost);`
with `renderToday(d); renderCalendar(d); renderProgram(d);`.

Add a temporary `function renderProgram(d) {}` (Task 4 replaces it).

- [ ] **Step 3: Tabs and pages**

Replace the remaining two `<section>`s (Today and Calendar) with:

```html
  <nav class="tabs" aria-label="Pages">
    <a href="#today">Today</a><a href="#program">Program</a><a href="#progress">Progress</a>
  </nav>

  <section id="page-today">
    <div class="today" id="today"></div>
    <div class="wnav"><h2>Weeks</h2>
      <button class="linkbtn" id="earlier" aria-label="One week earlier">‹</button>
      <button class="linkbtn" id="later" aria-label="One week later">›</button>
      <button class="linkbtn" id="zoom">All weeks</button></div>
    <div class="legend" id="legend"></div>
    <div class="cal-scroll"><div class="cal" id="cal"></div></div>
    <div class="card detail" id="detail"><span class="sub">Pick a day to see the plan, what you did, the score and the morning's recovery.</span></div>
  </section>

  <section id="page-program" hidden>
    <h2>This week and next</h2>
    <div id="program"></div>
    <h2>Route to race day</h2>
    <p class="sub">Planned kilometres for each week until the race.</p>
    <div class="route" id="route"></div>
  </section>

  <section id="page-progress" hidden>
    <h2>Progress</h2>
    <div class="card wait">
      <p>This page comes once the route and drift exist (build steps 2 and 4). It will show:</p>
      <ul>
        <li>the planned VDOT line, with a dot for each test you confirmed</li>
        <li>weekly volume planned against done, a tick or cross and the adherence score for each week</li>
        <li>pace adherence, a fitness curve, and your bests (1 km to half) for the last 4 weeks against the 4 before</li>
      </ul>
    </div>
  </section>
```

Add to the CSS, after `/* today */`:

```css
/* pages */
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); overflow-x: auto; }
.tabs a { font-family: var(--display); font-size: 16px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); text-decoration: none; padding: 8px 14px; border-bottom: 3px solid transparent; }
.tabs a[aria-current="page"] { color: var(--ink); border-bottom-color: var(--accent); }
.wnav { display: flex; align-items: center; gap: 8px; }
.wnav h2 { margin-right: auto; }
.wnav button:disabled { opacity: .35; cursor: default; }
.wait { color: var(--muted); }
.wait ul { margin: 6px 0 0; padding-left: 18px; }
.ico { width: 15px; height: 15px; flex: none; vertical-align: -2px; fill: none; stroke: currentColor;
  stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.big .ico { width: 26px; height: 26px; vertical-align: -3px; }
```

- [ ] **Step 4: Icon sprite and helpers**

Directly after `<div class="wrap">`, add:

```html
  <svg width="0" height="0" style="position:absolute" aria-hidden="true">
    <symbol id="i-run" viewBox="0 0 24 24"><path d="M3 17h12l3-2 3 1v3H3zM6 17l2-7 4 2 1-3"/></symbol>
    <symbol id="i-strength" viewBox="0 0 24 24"><path d="M6 7v10M18 7v10M3 10v4M21 10v4M6 12h12"/></symbol>
    <symbol id="i-ride" viewBox="0 0 24 24"><circle cx="6" cy="16" r="3.5"/><circle cx="18" cy="16" r="3.5"/><path d="M6 16l4-7h5l3 7M10 9l2 7"/></symbol>
    <symbol id="i-kite" viewBox="0 0 24 24"><path d="M12 3l6 7-6 7-6-7zM12 17c0 2-2 2-2 4"/></symbol>
    <symbol id="i-football" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 8l3.5 2.5-1.3 4h-4.4l-1.3-4z"/></symbol>
    <symbol id="i-dot" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/></symbol>
  </svg>
```

In the script, after `const KIND = ...`, add:

```js
// One icon per activity kind, so a day reads at a glance (spec, Dashboard). Runs of every kind wear the shoe.
const ICON = { easy: "run", quality: "run", long: "run", test: "run", run: "run",
  strength: "strength", ride: "ride", kite: "kite", football: "football" };
const icon = (kind) => `<svg class="ico" aria-hidden="true"><use href="#i-${ICON[kind] || "dot"}"/></svg>`;
const PAGES = ["today", "program", "progress"];
function showPage(name) {
  if (!PAGES.includes(name)) name = "today";
  PAGES.forEach((p) => {
    $(`page-${p}`).hidden = p !== name;
    const a = document.querySelector(`.tabs a[href="#${p}"]`);
    if (p === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}
window.addEventListener("hashchange", () => showPage(location.hash.slice(1)));
```

Just before the final `boot();` line, add `showPage(location.hash.slice(1));`.

- [ ] **Step 5: Check in the browser**

Run: `python3 -m http.server 8765 -d dashboard` and open `http://localhost:8765/index.html`.
Expected: light paper background even when the OS is in dark mode; three tabs with Today underlined; the Today cards and calendar still draw (old design); clicking Program shows the two headings and empty content; Progress shows the waiting panel; no console errors. Nothing scrolls sideways at 400 px.

- [ ] **Step 6: Commit**

```bash
git add dashboard/index.html
git commit -m "feat(dashboard): light theme, Today, Program and Progress tabs, activity icons

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Today page: how you are, last and next session, three week blocks

**Files:**
- Modify: `dashboard/index.html`

**Interfaces:**
- Consumes: Task 1 fields `last_session`, `next_session`, `days[].checkin.feel`; Task 2 ids and `icon()`; existing helpers `esc`, `fmt`, `parse`, `addDays`, `target`, `recBand`, `paceText`, `showDay`.
- Produces: `renderToday(d)`, `renderCalendar(d)` (three-week window), `chip(s, day)`, state `view = { offset, all }`.

- [ ] **Step 1: Chip styles coloured by recovery**

Replace the `.chip`, `.chip b`, `.chip .sc` rules and the `.st-upcoming` and `.st-missed b` rules with:

```css
.chip { display: flex; align-items: center; gap: 3px; font-size: 11.5px; line-height: 1.25; padding: 2px 4px;
  border-radius: 4px; border-left: 3px solid var(--line); background: var(--soft); }
/* A run is coloured by that morning's recovery (Whoop bands), not by its score. */
.chip.rec-hi { border-left-color: var(--rec-hi); background: color-mix(in srgb, var(--rec-hi) 18%, transparent); }
.chip.rec-mid { border-left-color: var(--rec-mid); background: color-mix(in srgb, var(--rec-mid) 18%, transparent); }
.chip.rec-lo { border-left-color: var(--rec-lo); background: color-mix(in srgb, var(--rec-lo) 18%, transparent); }
.chip.st-upcoming { background: transparent; border: 1px dashed var(--line); border-left-width: 3px; }
.chip.st-missed .tg { text-decoration: line-through; }
.chip.st-missed .mk { color: var(--missed); }
.chip .sc { margin-left: auto; font-family: var(--display); font-weight: 600; }
.icons { display: flex; gap: 4px; color: var(--muted); }
.card.rec-hi { border-top: 4px solid var(--rec-hi); } .card.rec-mid { border-top: 4px solid var(--rec-mid); }
.card.rec-lo { border-top: 4px solid var(--rec-lo); }
```

Keep the `.st-done` … `.st-excused` variable rules (Task 4 uses them). In the `@media (max-width: 520px)` block replace the three chip rules (`.chip {...}`, `.chip .sc, .chip b, .km {...}`, `.chip::before {...}`) with:

```css
  .chip { font-size: 10.5px; padding: 1px 2px; border-left-width: 2px; }
  .chip .sc, .chip .tg, .km { display: none; }
```

- [ ] **Step 2: Today cards**

Replace `renderToday` with:

```js
function renderToday(d) {
  const t = d.days.find((x) => x.date === d.today) || {};
  const ck = t.checkin, last = d.last_session, next = d.next_session;
  const how = [t.hrv != null ? `HRV ${t.hrv} ms` : "No Whoop reading yet",
    ck && ck.feel != null ? `feel ${ck.feel}/10` : "",
    ck ? `check-in: ${ck.decision}` : "check-in: not yet"].filter(Boolean);
  const lastLine = last && `${icon(last.kind)} ${esc(KIND[last.kind] || last.kind)} ${Math.round(last.minutes)}′${last.km ? ` · ${last.km.toFixed(1)} km` : ""}`;
  const s = next && next.session;
  $("today").innerHTML = `
    <div class="card ${t.recovery != null ? `rec-${recBand(t.recovery)}` : ""}">
      <div class="label">How you are · ${esc(fmt(d.today, { weekday: "long", day: "numeric", month: "long" }))}</div>
      <div class="big">${t.recovery != null ? `${Math.round(t.recovery)}%` : "–"}</div>
      <div class="sub">${how.map(esc).join(" · ")}</div></div>
    <div class="card"><div class="label">Last session</div>
      ${last ? `<div class="big">${lastLine}</div><div class="sub">${esc(fmt(last.date, { weekday: "long", day: "numeric", month: "short" }))}${last.recovery != null ? esc(` · recovery that morning ${Math.round(last.recovery)}%`) : ""}</div>`
             : `<div class="sub">Nothing recorded yet.</div>`}</div>
    <div class="card"><div class="label">Next session</div>
      ${s ? `<div class="big">${icon(s.kind)} ${esc(KIND[s.kind] || s.kind)} ${esc(target(s.target, s.unit))}</div>
             <div class="sub">${esc(fmt(next.date, { weekday: "long", day: "numeric", month: "short" }))}${paceText(s)}${s.zone_max ? ` · zone ${s.zone_max} max` : ""}</div>`
          : `<div class="sub">No session planned.</div>`}</div>`;
}
```

Note: `paceText` escapes the structure itself; `pace` is one of the validated pace kinds and the band is computed, so the line is not wrapped in `esc()` again (that would show `&amp;`).

- [ ] **Step 3: Three week blocks with earlier, later and zoom out**

Replace `chip` and `renderCalendar` with:

```js
const MARK = { done: "✓", over: "✓", short: "~", moved: "↔", missed: "✗", excused: "rest", upcoming: "" };
let view = { offset: 0, all: false };   // weeks shifted from the default last / this / next window

function chip(s, day) {
  const sc = s.score || { status: "upcoming" }, st = sc.status;
  const [t, u] = sc.adjusted ? [sc.planned, sc.unit] : [s.target, s.unit];
  const rec = ["done", "over", "short"].includes(st) && day.recovery != null ? `rec-${recBand(day.recovery)}` : "";
  const score = sc.adherence != null && st !== "upcoming" && st !== "excused" ? `<span class="sc">${Math.round(sc.adherence)}</span>` : "";
  return `<div class="chip st-${st} ${rec}" title="${esc(`${KIND[s.kind] || s.kind}: ${st}`)}">${icon(s.kind)}<span class="mk">${MARK[st]}</span><span class="tg">${esc(target(t, u))}</span>${score}</div>`;
}

function extras(day) {
  // Activities that were not planned, as icons. Walks and unnamed movement stay in the day detail.
  const kinds = new Set(day.done.filter((a) => !["walk", "other"].includes(a.kind) &&
    !day.planned.some((p) => ICON[p.kind] === ICON[a.kind])).map((a) => a.kind));
  return kinds.size ? `<div class="icons">${[...kinds].map((k) => `<span title="${esc(KIND[k] || k)}">${icon(k)}</span>`).join("")}</div>` : "";
}

function renderCalendar(d) {
  $("legend").innerHTML = `<span class="chip rec-hi">recovery 67%+</span><span class="chip rec-mid">34-66%</span>` +
    `<span class="chip rec-lo">under 34%</span><span>✓ done · ~ short · ✗ missed · ↔ moved · number = score</span>`;
  const rows = [];
  for (let i = 0; i < d.days.length; i += 7) rows.push(d.days.slice(i, i + 7));
  const cur = Math.max(0, rows.findIndex((r) => r.some((x) => x.date === d.today)));
  const maxLo = Math.max(0, rows.length - 3);
  const lo = view.all ? 0 : Math.min(maxLo, Math.max(0, cur - 1 + view.offset));
  const hi = view.all ? rows.length : Math.min(rows.length, lo + 3);
  $("earlier").disabled = view.all || lo === 0;
  $("later").disabled = view.all || hi >= rows.length;
  $("zoom").textContent = view.all ? "Three weeks" : "All weeks";
  const weeks = new Map(d.weeks.map((w) => [w.start, w]));
  let html = `<div></div>` + ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((x) => `<div class="dow">${x}</div>`).join("");
  rows.slice(lo, hi).forEach((row) => {
    const w = weeks.get(row[0].date);
    html += `<div class="wl"><span>${esc(fmt(row[0].date, { day: "numeric", month: "short" }))}</span>${w && w.adherence != null ? `<span class="num">${Math.round(w.adherence)}</span>` : ""}</div>`;
    row.forEach((day) => {
      const ck = day.checkin ? `<span class="ck" title="check-in: ${esc(day.checkin.decision)}">${esc(day.checkin.decision[0].toUpperCase())}</span>` : "";
      html += `<button class="day ${day.date === d.today ? "today" : ""} ${day.date > d.today ? "future" : ""}" data-date="${day.date}" aria-label="${esc(fmt(day.date, { weekday: "long", day: "numeric", month: "long" }))}">
        <span class="dn"><span>${parse(day.date).getDate()}</span>${ck}</span>
        ${day.planned.map((s) => chip(s, day)).join("")}${extras(day)}
        ${day.recovery != null ? `<span class="rec ${recBand(day.recovery)}" title="recovery ${Math.round(day.recovery)}%"></span>` : ""}
      </button>`;
    });
  });
  $("cal").innerHTML = html;
}

function moveWeeks(change) {
  if (change === "zoom") view.all = !view.all; else view.offset += change;
  renderCalendar(data);
  if (selected) showDay(selected);
}
$("earlier").addEventListener("click", () => moveWeeks(-1));
$("later").addEventListener("click", () => moveWeeks(1));
$("zoom").addEventListener("click", () => moveWeeks("zoom"));
```

Delete the now-unused `doneLine` function and the `STATUS` constant. `render()` stays as it is: `showDay` reads the day from `data`, so a selected day outside the window still shows its detail.

Clamp `view.offset` after a move so it never runs past the data: in `moveWeeks`, after `view.offset += change`, add
`view.offset = Math.max(-(data.days.length / 7), Math.min(data.days.length / 7, view.offset));`

- [ ] **Step 4: Check in the browser**

Open `http://localhost:8765/index.html` (demo).
Expected:
- Three cards: "How you are" with 71%-style recovery and a coloured top edge, "Last session" with a shoe or other icon and the date, "Next session" reading Quality 50′ with "6 x 3 min threshold 4:11-4:21/km".
- Exactly three week rows (30 Nov, 7 Dec, 14 Dec); ‹ moves to 23 Nov, › comes back; › is disabled on the last row; "All weeks" shows all ten and greys out ‹ ›.
- Past runs are green, yellow or red with ✓ / ~ / ✗ and a score; future runs are dashed; football and gym show their icons.
- At 400 px the cells show icon and mark only; no horizontal page scroll.

- [ ] **Step 5: Commit**

```bash
git add dashboard/index.html
git commit -m "feat(dashboard): Today page with last and next session and three week blocks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Program page: sessions with pace and purpose, then the route

**Files:**
- Modify: `dashboard/index.html`

**Interfaces:**
- Consumes: Task 1 fields `days[].planned[].purpose`, `route`; Task 2 ids `program`, `route` and `icon()`; existing `paceText`, `target`, `fmt`, `parse`, `addDays`, `ymd`.
- Produces: `renderProgram(d)` (replaces the stub from Task 2).

- [ ] **Step 1: Styles**

Add to the CSS after `/* pages */`:

```css
/* program */
.pweek { display: grid; gap: 8px; }
.pweek h3 { font-family: var(--display); font-size: 15px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin: 8px 0 0; }
.prow { display: grid; grid-template-columns: 48px 1fr; gap: 12px; background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; }
.prow.today { outline: 2px solid var(--accent); outline-offset: 1px; }
.pday { display: grid; justify-items: center; align-content: start; }
.pday .num { font-size: 24px; font-weight: 600; line-height: 1; }
.pbody { display: grid; gap: 2px; min-width: 0; }
.ptitle { font-size: 16px; }
.pmeta { font-family: var(--display); font-size: 15px; font-variant-numeric: tabular-nums; }
.pres { font-size: 13px; color: var(--st, var(--muted)); font-weight: 600; }
.route { display: grid; gap: 4px; }
.rrow { display: grid; grid-template-columns: 64px 1fr 56px 84px; gap: 10px; align-items: center; font-size: 13px; }
.rtrack { height: 12px; background: var(--soft); border-radius: 2px; }
.rfill { height: 100%; border-radius: 2px; background: var(--ink); }
.rfill.t-recovery { background: var(--muted); }
.rrow small { color: var(--muted); }
@media (max-width: 520px) { .rrow { grid-template-columns: 52px 1fr 52px; } .rrow small { display: none; } }
```

- [ ] **Step 2: Render**

Replace the stub `function renderProgram(d) {}` with:

```js
function programRow(day, s, today) {
  const sc = s.score || { status: "upcoming" }, st = sc.status;
  const result = st === "upcoming" ? "" : [st,
    sc.actual != null && st !== "missed" && st !== "excused" ? `${target(sc.actual, sc.unit)} done` : "",
    sc.adherence != null && st !== "excused" ? `score ${Math.round(sc.adherence)}` : ""].filter(Boolean).join(" · ");
  const meta = [s.pace ? `${s.pace} ${s.pace_band || "(band after your first confirmed test)"}` : "",
    s.zone_max ? `heart rate zone ${s.zone_max} max` : ""].filter(Boolean).join(" · ");
  return `<article class="prow ${day.date === today ? "today" : ""}">
    <div class="pday"><span class="label">${esc(fmt(day.date, { weekday: "short" }))}</span><span class="num">${parse(day.date).getDate()}</span></div>
    <div class="pbody">
      <div class="ptitle">${icon(s.kind)} <b>${esc(KIND[s.kind] || s.kind)} ${esc(target(s.target, s.unit))}</b>${s.structure ? ` · ${esc(s.structure)}` : ""}</div>
      ${meta ? `<div class="pmeta">${esc(meta)}</div>` : ""}
      ${s.purpose ? `<div class="sub">${esc(s.purpose)}</div>` : ""}
      ${s.note ? `<div class="sub">${esc(s.note)}</div>` : ""}
      ${result ? `<div class="pres st-${st}">${esc(result)}</div>` : ""}
    </div></article>`;
}

function renderProgram(d) {
  const t = parse(d.today), mon = addDays(t, -((t.getDay() + 6) % 7));
  $("program").innerHTML = [[mon, "This week"], [addDays(mon, 7), "Next week"]].map(([m, label]) => {
    const from = ymd(m), to = ymd(addDays(m, 6));
    const rows = d.days.filter((x) => x.date >= from && x.date <= to)
      .flatMap((day) => day.planned.map((s) => programRow(day, s, d.today)));
    return `<div class="pweek"><h3>${label} · ${esc(fmt(from, { day: "numeric", month: "short" }))}</h3>${rows.join("") || `<p class="sub">No sessions planned.</p>`}</div>`;
  }).join("") + `<p class="sub wait">Coming with lap analysis (spec D33): whether each run matched its structure and pace band, for example “3 of 3 blocks in band”. Until then a past session shows its volume and score.</p>`;
  const route = d.route || [];
  const max = Math.max(1, ...route.map((w) => w.km || 0));
  $("route").innerHTML = route.length ? route.map((w) => `<div class="rrow">
      <span>${esc(fmt(w.start, { day: "numeric", month: "short" }))}</span>
      <div class="rtrack"><div class="rfill t-${esc(w.type)}" style="width:${(100 * (w.km || 0) / max).toFixed(1)}%"></div></div>
      <span class="num">${esc(w.km)} km</span><small>${esc(w.type)}</small></div>`).join("")
    : `<p class="sub">No confirmed plan yet.</p>`;
}
```

- [ ] **Step 3: Check in the browser**

Open `http://localhost:8765/index.html#program` (demo).
Expected: "This week · 7 Dec" lists Mon easy (done, with score), Wed quality outlined as today, with "6 x 3 min" in the title, "threshold 4:11-4:21/km" and its purpose; Sun long with "heart rate zone 2 max"; "Next week · 14 Dec" lists upcoming rows with no result line; the D33 note; then route bars for 7 Dec and 14 Dec, the recovery week greyer. Reloading on `#program` opens Program directly. At 400 px rows stack without sideways scroll.

- [ ] **Step 4: Run the suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: 154 passed.

```bash
git add dashboard/index.html
git commit -m "feat(dashboard): Program page with session pace, purpose and the route

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## After the plan (controller, not a task)

Republish the private artifact https://claude.ai/artifact/VYoBy2v1SFq7dK1nW9HZct from a content-only copy of `dashboard/index.html` (strip doctype, html, head, body, charset and viewport tags) with `demo-data.json` alongside, keeping its stored capabilities. Live mode needs a Cmd+Q restart of the Claude app so coach-core serves the new fields.
