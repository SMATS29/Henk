"""Pytest fixtures voor Henk tests."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from henk.config import Config, DEFAULT_CONFIG, _deep_merge


@pytest.fixture
def tmp_henk_dir(tmp_path):
    """Maak een tijdelijke henk data directory aan."""
    data_dir = tmp_path / "henk"
    dirs = [
        data_dir / "memory" / "active",
        data_dir / "memory" / "episodes",
        data_dir / "memory" / ".staged",
        data_dir / "workspace",
        data_dir / "skills",
        data_dir / "control",
        data_dir / "tools" / "user",
        data_dir / "tools" / "generated",
        data_dir / "tools" / "external",
        data_dir / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Core memory
    (data_dir / "memory" / "core.md").write_text("# Henk — Kerngeheugen\n", encoding="utf-8")

    # Control files
    (data_dir / "control" / "graceful_stop").write_text("false", encoding="utf-8")
    (data_dir / "control" / "hard_stop").write_text("false", encoding="utf-8")

    return data_dir


@pytest.fixture
def config(tmp_henk_dir):
    """Config met paden naar tmp directory."""
    data = _deep_merge(DEFAULT_CONFIG, {
        "paths": {
            "data_dir": str(tmp_henk_dir),
            "memory_dir": str(tmp_henk_dir / "memory"),
            "workspace_dir": str(tmp_henk_dir / "workspace"),
            "logs_dir": str(tmp_henk_dir / "logs"),
            "control_dir": str(tmp_henk_dir / "control"),
        }
    })
    return Config(data)


@pytest.fixture
def mock_brain(config):
    """Een mock Brain die geen API calls doet."""
    brain = MagicMock()
    brain.think.return_value = "Test antwoord van Henk."
    brain.greet.return_value = "Hoi, ik ben Henk."
    return brain
