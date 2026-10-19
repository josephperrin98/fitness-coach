"""The validation layer: the gate every proposed plan has to pass.

Plain code, no model calls. A plan change is only as safe as the rules that
check it, so the rules are deterministic, tested, and carry their provenance.

Tiers
  hard  -> the plan is rejected
  soft  -> the plan can be confirmed only if the user acknowledges the rule id
  (a third tier, LLM judgment, is intentionally NOT in this module: it advises,
   it never blocks.)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .plan import LOADING_TYPES, Plan, Week
from .rules import RuleSet, load_rules

_EPS = 1e-9


@dataclass(frozen=True)
class Violation:
    rule: str
    tier: str          # hard | soft  (the tier of this finding)
    status: str        # decided | proposed (how settled the rule itself is)
    source: str        # provenance category of the rule
    week: date | None
    message: str

    def __str__(self) -> str:
        where = self.week.isoformat() if self.week else "plan"
        return f"[{self.tier.upper()}] {self.rule} ({where}): {self.message}  <{self.source}, {self.status}>"


def validate(plan: Plan, rules: RuleSet | None = None) -> list[Violation]:
    rules = rules or load_rules()
    out: list[Violation] = []

    def flag(rule_id: str, tier: str, week: Week, message: str) -> None:
        r = rules[rule_id]
        out.append(Violation(rule_id, tier, r.status, r.source, week.start, message))

    weeks = plan.weeks
    rec = rules["R-REC-1"].params
    load = rules["R-LOAD-1"].params

    peak = 0.0            # highest km in the current block (since last recovery)
    last_peak = 0.0       # the block peak that the most recent recovery week followed
    prev_was_recovery = False
    streak = 0            # consecutive loading weeks

    for i, w in enumerate(weeks):
        prev = weeks[i - 1] if i > 0 else None

        # --- is this an (effective) recovery week? -------------------------
        declared = w.type == "recovery"
        life_recovery = (
            w.life_event and w.type in LOADING_TYPES and peak > 0
            and w.km <= rec["life_event_fraction"] * peak + _EPS
        )
        is_recovery = declared or life_recovery

        # --- R-REC-1: what a recovery week must look like ------------------
        if declared:
            if w.runs > rec["max_runs"]:
                flag("R-REC-1", "hard", w, f"{w.runs} runs; recovery weeks allow at most {rec['max_runs']}")
            if w.quality > rec["max_quality"]:
                flag("R-REC-1", "hard", w, "recovery weeks have no quality sessions")
            if w.long_run_km > rec["max_long_run_km"] + _EPS:
                flag("R-REC-1", "hard", w, f"long run {w.long_run_km:g} km exceeds {rec['max_long_run_km']} km")
            if w.football > rec["max_football"]:
                flag("R-REC-1", "hard", w, "no football in recovery weeks")
            if peak > 0 and w.km > rec["max_fraction_of_block_peak"] * peak + _EPS:
                cap = rec["max_fraction_of_block_peak"] * peak
                flag("R-REC-1", "hard", w, f"{w.km:g} km exceeds {cap:.1f} km "
                     f"({rec['max_fraction_of_block_peak']:.0%} of block peak {peak:g} km)")

        # --- R-REC-2: restart below the last peak --------------------------
        if prev_was_recovery and not is_recovery and w.type in LOADING_TYPES and last_peak > 0:
            cap = rules["R-REC-2"].params["max_fraction_of_last_peak"] * last_peak
            if w.km > cap + _EPS:
                flag("R-REC-2", "soft", w, f"restart week {w.km:g} km exceeds {cap:.1f} km "
                     f"({rules['R-REC-2'].params['max_fraction_of_last_peak']:.0%} of last peak {last_peak:g} km)")

        # --- R-LOAD-1: week-over-week cap (not after a recovery week) ------
        if prev and not prev_was_recovery and not is_recovery and prev.km > 0 and w.type != "race":
            soft_cap = _cap(prev.km, load["soft_pct"], load)
            hard_cap = _cap(prev.km, load["hard_pct"], load)
            if w.km > hard_cap + _EPS:
                flag("R-LOAD-1", "hard", w, f"{prev.km:g} -> {w.km:g} km (+{(w.km / prev.km - 1):.0%}) "
                     f"is above the hard cap of {hard_cap:.1f} km")
            elif w.km > soft_cap + _EPS:
                flag("R-LOAD-1", "soft", w, f"{prev.km:g} -> {w.km:g} km (+{(w.km / prev.km - 1):.0%}) "
                     f"is above the soft cap of {soft_cap:.1f} km")

        # --- R-REC-3: too many loading weeks in a row ----------------------
        if is_recovery or w.type not in LOADING_TYPES:
            streak = 0
        else:
            streak += 1
            max_streak = rules["R-REC-3"].params["max_loading_weeks"]
            if streak > max_streak:
                flag("R-REC-3", "soft", w, f"{streak} loading weeks in a row; recovery due after {max_streak}")

        # --- R-FREQ-1: frequency ceiling and 5th-run window ----------------
        f1 = rules["R-FREQ-1"].params
        if w.runs > f1["hard_ceiling"]:
            flag("R-FREQ-1", "hard", w, f"{w.runs} runs exceeds the ceiling of {f1['hard_ceiling']}")
        elif w.runs > f1["typical_max"] and w.type not in f1["five_run_week_types"]:
            flag("R-FREQ-1", "hard", w, f"{w.runs} runs: a 5th run is only allowed in "
                 f"{', '.join(f1['five_run_week_types'])} weeks")

        # --- R-FOOT-1: football by week type -------------------------------
        foot = rules["R-FOOT-1"].params[w.type]
        if "max_per_week" in foot and w.football > foot["max_per_week"]:
            flag("R-FOOT-1", "hard", w, f"{w.football} football in a {w.type} week; max {foot['max_per_week']}")
        if "max_per_window" in foot:
            window = _same_type_window(weeks, i, w.type, foot["window_weeks"])
            total = sum(x.football for x in window)
            if total > foot["max_per_window"]:
                flag("R-FOOT-1", "hard", w, f"{total} football in {len(window)} consecutive {w.type} weeks; "
                     f"max {foot['max_per_window']} per {foot['window_weeks']}")

        # --- R-INT-1: hard sessions per week -------------------------------
        cap_q = rules["R-INT-1"].params["max_quality_per_week"]
        if w.quality > cap_q:
            flag("R-INT-1", "hard", w, f"{w.quality} quality sessions; max {cap_q} per week")

        # --- bookkeeping for the next iteration ----------------------------
        if is_recovery:
            if peak > 0:
                last_peak = peak
            peak = 0.0
        else:
            peak = max(peak, w.km)
        prev_was_recovery = is_recovery

    _check_five_run_blocks(plan, rules, flag)
    return sorted(out, key=lambda v: (v.week or date.min, v.rule))


def _cap(prev_km: float, pct: float, p: dict) -> float:
    cap = prev_km * (1 + pct)
    if prev_km < p["small_base_km"]:
        cap = max(cap, prev_km + p["small_base_abs_km"])
    return cap


def _same_type_window(weeks: tuple[Week, ...], i: int, wtype: str, size: int) -> list[Week]:
    window = [weeks[i]]
    for j in range(i - 1, max(i - size, -1), -1):
        if weeks[j].type != wtype:
            break
        window.append(weeks[j])
    return window


def _check_five_run_blocks(plan: Plan, rules: RuleSet, flag) -> None:
    """R-FREQ-2: cap 5-run weeks per race-specific block, and consecutive ones."""
    p = rules["R-FREQ-2"].params
    max_total = p["max_five_run_weeks_per_block"][plan.goal]
    max_consec = p["max_consecutive_five_run_weeks"]
    total = consec = 0
    for w in plan.weeks:
        if w.type != "race_specific":
            total = consec = 0
            continue
        if w.runs >= 5:
            total += 1
            consec += 1
            if total > max_total:
                flag("R-FREQ-2", "soft", w, f"{total} five-run weeks in this block; max {max_total} for a {plan.goal}")
            elif consec > max_consec:
                flag("R-FREQ-2", "soft", w, f"{consec} five-run weeks in a row; max {max_consec}")
        else:
            consec = 0
