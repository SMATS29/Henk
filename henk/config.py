"""Configuratie laden uit henk.yaml en .env."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


DEFAULT_CONFIG = {
    "henk": {"name": "Henk", "language": "nl"},
    "provider": {"default": "openai", "model": "gpt-5-mini"},
    "security": {
        "react_loop": {
            "max_tool_calls": 4,
            "max_retries_content": 2,
            "max_retries_technical": 1,
            "identical_call_detection": True,
        }
    },
    "ui": {"pipe_name": "henk-gateway", "history_hours": 24},
    "paths": {
        "data_dir": "~/henk",
        "memory_dir": "~/henk/memory",
        "workspace_dir": "~/henk/workspace",
        "logs_dir": "~/henk/logs",
        "control_dir": "~/henk/control",
    },
}


class Config:
    """Henk configuratie."""

    def __init__(self, data: dict):
        self._data = data

    @property
    def model(self) -> str:
        return self._data["provider"]["model"]

    @property
    def provider(self) -> str:
        return self._data["provider"]["default"]

    @property
    def api_key_env_var(self) -> str:
        """Geef de naam van de env var voor de actieve provider."""
        key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
        }
        return key_map.get(self.provider, f"{self.provider.upper()}_API_KEY")

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env_var)

    @property
    def data_dir(self) -> Path:
        return Path(self._data["paths"]["data_dir"]).expanduser()

    @property
    def memory_dir(self) -> Path:
        return Path(self._data["paths"]["memory_dir"]).expanduser()

    @property
    def workspace_dir(self) -> Path:
        return Path(self._data["paths"]["workspace_dir"]).expanduser()

    @property
    def logs_dir(self) -> Path:
        return Path(self._data["paths"]["logs_dir"]).expanduser()

    @property
    def control_dir(self) -> Path:
        return Path(self._data["paths"]["control_dir"]).expanduser()

    @property
    def max_tool_calls(self) -> int:
        return self._data["security"]["react_loop"]["max_tool_calls"]

    @property
    def max_retries_content(self) -> int:
        return self._data["security"]["react_loop"]["max_retries_content"]

    @property
    def max_retries_technical(self) -> int:
        return self._data["security"]["react_loop"]["max_retries_technical"]

    @property
    def raw(self) -> dict:
        return self._data


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(data_dir: Path | None = None) -> Config:
    """Laad configuratie uit .env en henk.yaml."""
    # Laad .env vanuit repo root en huidige directory
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path(__file__).parent.parent / ".env")

    # Bepaal data directory
    if data_dir is None:
        data_dir = Path.home() / "henk"

    config_path = data_dir / "henk.yaml"
    data = DEFAULT_CONFIG.copy()

    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            file_data = yaml.safe_load(f)
        if file_data:
            data = _deep_merge(DEFAULT_CONFIG, file_data)

    return Config(data)
