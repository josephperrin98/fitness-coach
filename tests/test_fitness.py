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
