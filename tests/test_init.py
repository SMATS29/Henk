"""Tests voor henk init."""

from pathlib import Path

from typer.testing import CliRunner

from henk.cli import app

runner = CliRunner()


def test_init_creates_directories(tmp_path, monkeypatch):
    """henk init maakt alle mappen correct aan."""
    data_dir = tmp_path / "henk"
    monkeypatch.setattr("henk.cli._get_data_dir", lambda: data_dir)

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    expected_dirs = [
        "memory/active",
        "memory/episodes",
        "memory/.staged/pending",
        "memory/.staged/archive",
        "workspace",
        "skills",
        "control",
        "tools/user",
        "tools/generated",
        "tools/external",
        "logs",
    ]
    for d in expected_dirs:
        assert (data_dir / d).is_dir(), f"Directory {d} niet aangemaakt"


def test_init_creates_files(tmp_path, monkeypatch):
    """henk init maakt alle bestanden correct aan."""
    data_dir = tmp_path / "henk"
    monkeypatch.setattr("henk.cli._get_data_dir", lambda: data_dir)

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    # Core memory
    core_md = data_dir / "memory" / "core.md"
    assert core_md.exists()
    assert "Kerngeheugen" in core_md.read_text(encoding="utf-8")

    # Control files
    assert (data_dir / "control" / "graceful_stop").read_text(encoding="utf-8") == "false"
    assert (data_dir / "control" / "hard_stop").read_text(encoding="utf-8") == "false"

    # Config
    config_path = data_dir / "henk.yaml"
    assert config_path.exists()
    config_text = config_path.read_text(encoding="utf-8")
    assert "providers:" in config_text
    assert "roles:" in config_text
    assert "user_name:" in config_text
    assert "identity_prompt_enabled: false" in config_text
    assert "primary: openai/gpt-5.2" in config_text


def test_init_existing_no_overwrite(tmp_path, monkeypatch):
    """henk init op bestaande installatie overschrijft niets bij 'nee'."""
    data_dir = tmp_path / "henk"
    data_dir.mkdir()
    marker = data_dir / "marker.txt"
    marker.write_text("bewijs", encoding="utf-8")
    monkeypatch.setattr("henk.cli._get_data_dir", lambda: data_dir)

    result = runner.invoke(app, ["init"], input="n\n")

    assert marker.read_text(encoding="utf-8") == "bewijs"


def test_init_existing_yes_reinit(tmp_path, monkeypatch):
    """henk init op bestaande installatie herïnitialiseert bij 'ja'."""
    data_dir = tmp_path / "henk"
    data_dir.mkdir()
    monkeypatch.setattr("henk.cli._get_data_dir", lambda: data_dir)

    result = runner.invoke(app, ["init"], input="y\n")
    assert result.exit_code == 0
    assert (data_dir / "memory" / "core.md").exists()
