"""Checkpoints (D31): the athlete's confirmed test results. Textbook values only."""
from datetime import date

import pytest

from coach.checkpoints import Checkpoint, CheckpointStore


def test_records_and_returns_the_latest_as_of_a_day():
    store = CheckpointStore()
    store.record(Checkpoint(day=date(2026, 10, 22), kind="5k", distance_m=5000, seconds=1260))
    store.record(Checkpoint(day=date(2026, 11, 20), kind="5k", distance_m=5000, seconds=1200))
    assert store.latest(date(2026, 11, 1)).seconds == 1260
    assert store.latest(date(2026, 11, 20)).vdot == pytest.approx(49.8, abs=0.05)
    assert store.latest(date(2026, 10, 1)) is None


def test_refuses_unknown_kinds_and_impossible_results():
    with pytest.raises(ValueError, match="kind"):
        Checkpoint(day=date(2026, 10, 22), kind="vibes", distance_m=5000, seconds=1200)
    with pytest.raises(ValueError, match="positive"):
        Checkpoint(day=date(2026, 10, 22), kind="5k", distance_m=5000, seconds=0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_refuses_non_finite_results(bad):
    with pytest.raises(ValueError, match="positive"):
        Checkpoint(day=date(2026, 10, 22), kind="5k", distance_m=5000, seconds=bad)
