"""Paces from VDOT (D29-D31). Textbook values only: this repo is public."""
import pytest

from coach.rules import load_rules


def test_pace_rules_load_with_provenance():
    paces = load_rules().paces
    assert paces["intensity"]["threshold"] == [0.86, 0.90]
    assert paces["progression"]["cap_above_checkpoint"] == 1.0
    assert paces["progression"]["target_lead_days"] == 14


def test_pace_rules_without_provenance_are_refused(tmp_path):
    bad = tmp_path / "rules.yaml"
    bad.write_text('version: "x"\nrules: {}\npaces:\n  intensity: {easy: [0.6, 0.7]}\n'
                   '  progression: {cap_above_checkpoint: 1.0, target_lead_days: 14}\n')
    with pytest.raises(ValueError, match="paces.intensity"):
        load_rules(bad)


from coach.fitness import RACE_METRES, fmt_pace, pace_band, race_seconds, vdot

INTENSITY = load_rules().paces["intensity"]


def test_vdot_matches_daniels_table():
    assert vdot(5000, 20 * 60) == pytest.approx(49.8, abs=0.05)        # Daniels: 5 km 20:00 = 49.8
    assert vdot(RACE_METRES["half"], 90 * 60) == pytest.approx(51.0, abs=0.05)


def test_race_seconds_inverts_vdot():
    assert race_seconds(vdot(5000, 1200), 5000) == pytest.approx(1200, abs=1)
    assert race_seconds(50.0, RACE_METRES["half"]) == pytest.approx(5491, abs=2)


def test_pace_bands_at_vdot_50():
    assert pace_band(50.0, "easy", INTENSITY) == (307, 338)
    assert pace_band(50.0, "long", INTENSITY) == (307, 338)
    assert pace_band(50.0, "threshold", INTENSITY) == (251, 260)
    assert pace_band(50.0, "interval", INTENSITY) == (230, 240)


def test_race_pace_band_is_predicted_race_pace_plus_minus_one_percent():
    fast, slow = pace_band(50.0, "race", INTENSITY, race_m=RACE_METRES["half"])
    assert (fast, slow) == (258, 263)


def test_race_pace_needs_a_race_distance():
    with pytest.raises(ValueError, match="race distance"):
        pace_band(50.0, "race", INTENSITY)


def test_fmt_pace():
    assert fmt_pace(260) == "4:20"
    assert fmt_pace(299.6) == "5:00"


from datetime import date

from coach.fitness import pace_vdot, vdot_line
from coach.plan import Week


def _weeks(*types):
    return tuple(Week(start=date(2026, 11, 2 + 7 * i), type=t, runs=3, km=20) for i, t in enumerate(types))


def test_line_rises_in_loading_weeks_and_holds_in_recovery():
    weeks = _weeks("foundation", "foundation", "recovery", "build", "taper")
    line = vdot_line(weeks, date(2026, 11, 3), 48.0, date(2026, 11, 23), 50.0)
    assert [line[w.start] for w in weeks] == [48.0, 49.0, 49.0, 50.0, 50.0]


def test_line_is_flat_when_already_at_target():
    weeks = _weeks("foundation", "build")
    line = vdot_line(weeks, date(2026, 11, 2), 51.0, date(2026, 11, 9), 50.0)
    assert list(line.values()) == [51.0, 51.0]


def test_line_ignores_weeks_before_the_checkpoint():
    weeks = _weeks("foundation", "foundation", "build")
    line = vdot_line(weeks, date(2026, 11, 10), 48.0, date(2026, 11, 16), 49.0)
    assert date(2026, 11, 2) not in line and line[date(2026, 11, 16)] == 49.0


def test_paces_never_assume_more_than_the_cap_above_the_last_test():
    assert pace_vdot(52.0, 48.0, 1.0) == 49.0
    assert pace_vdot(48.5, 48.0, 1.0) == 48.5
