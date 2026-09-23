# tests/test_smoke.py
"""Proves the package is importable from the installed environment."""
import fitness_app
import fitness_app.whoop


def test_package_imports():
    assert fitness_app is not None
    assert fitness_app.whoop is not None
