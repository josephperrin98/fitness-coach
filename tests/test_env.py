# tests/test_env.py
from fitness_app import env


def test_load_dotenv_sets_missing_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("DEMO_A", raising=False)
    (tmp_path / ".env").write_text('DEMO_A=hello\n# comment\n\nDEMO_B="quoted"\n')
    env.load_dotenv(tmp_path / ".env")
    import os
    assert os.environ["DEMO_A"] == "hello"
    assert os.environ["DEMO_B"] == "quoted"
    monkeypatch.delenv("DEMO_A")
    monkeypatch.delenv("DEMO_B")


def test_load_dotenv_does_not_override_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_A", "from-shell")
    (tmp_path / ".env").write_text("DEMO_A=from-file\n")
    env.load_dotenv(tmp_path / ".env")
    import os
    assert os.environ["DEMO_A"] == "from-shell"


def test_load_dotenv_ignores_missing_file(tmp_path):
    env.load_dotenv(tmp_path / "nope")  # must not raise
