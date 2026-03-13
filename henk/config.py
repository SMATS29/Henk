"""Configuratie laden uit henk.yaml en .env."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


DEFAULT_CONFIG: dict[str, Any] = {
    "henk": {"name": "Henk", "language": "nl"},
    "providers": {
        "anthropic": {"api_key_env": "ANTHROPIC_API_KEY"},
        "openai": {"api_key_env": "OPENAI_API_KEY"},
        "ollama": {"base_url": "http://localhost:11434/v1"},
        "lmstudio": {"base_url": "http://localhost:1234/v1"},
        "deepseek": {"api_key_env": "DEEPSEEK_API_KEY"},
    },
    "roles": {
        "fast": {"primary": "anthropic/claude-haiku-4-5", "fallback": ["ollama/qwen2.5:3b"]},
        "default": {
            "primary": "anthropic/claude-sonnet-4-6",
            "fallback": ["openai/gpt-4o", "deepseek/deepseek-chat"],
        },
        "heavy": {
            "primary": "anthropic/claude-opus-4-6",
            "fallback": ["anthropic/claude-sonnet-4-6"],
        },
    },
    "security": {
        "proxy": {
            "enabled": True,
            "allowed_domains": [
                "google.com",
                "www.google.com",
                "wikipedia.org",
                "en.wikipedia.org",
                "nl.wikipedia.org",
                "nos.nl",
                "reddit.com",
                "www.reddit.com",
            ],
            "allowed_methods": ["GET"],
        },
        "react_loop": {
            "max_tool_calls": 4,
            "max_retries_content": 2,
            "max_retries_technical": 1,
            "identical_call_detection": True,
        },
        "file_manager": {
            "read_roots": ["~/henk/memory", "~/henk/workspace"],
            "write_scope": "workspace_only",
        },
        "code_runner": {
            "max_cpu_seconds": 30,
            "max_memory_mb": 512,
            "max_runtime_seconds": 60,
            "network": False,
        },
    },
    "tools": {
        "web_search": {"enabled": True, "timeout_seconds": 10},
        "file_manager": {"enabled": True},
        "code_runner": {"enabled": True},
        "reminder": {"enabled": True},
    },
    "skills": {"dir": "~/henk/skills", "enabled": True},
    "heartbeat": {"enabled": True, "interval_seconds": 30},
    "memory": {
        "vector": True,
        "relevance_threshold": 0.3,
        "review_schedule": "daily",
        "store_third_party_pii": False,
        "scoring": {
            "initial_score": 50,
            "decay_per_week": 10,
            "use_boost": 10,
            "archive_threshold": 10,
        },
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
    def __init__(self, data: dict[str, Any]):
        self._data = data

    @property
    def providers_config(self) -> dict[str, Any]:
        return self._data.get("providers", {})

    @property
    def roles_config(self) -> dict[str, Any]:
        return self._data.get("roles", {})

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
        return int(self._data["security"]["react_loop"]["max_tool_calls"])

    @property
    def max_retries_content(self) -> int:
        return int(self._data["security"]["react_loop"]["max_retries_content"])

    @property
    def max_retries_technical(self) -> int:
        return int(self._data["security"]["react_loop"]["max_retries_technical"])

    @property
    def proxy_allowed_domains(self) -> list[str]:
        return list(self._data["security"]["proxy"]["allowed_domains"])

    @property
    def proxy_allowed_methods(self) -> list[str]:
        return list(self._data["security"]["proxy"]["allowed_methods"])

    @property
    def file_manager_read_roots(self) -> list[Path]:
        return [Path(path).expanduser() for path in self._data["security"]["file_manager"]["read_roots"]]

    @property
    def code_runner_timeout_seconds(self) -> int:
        return int(self._data["security"]["code_runner"]["max_runtime_seconds"])

    @property
    def web_search_timeout_seconds(self) -> int:
        return int(self._data["tools"]["web_search"]["timeout_seconds"])

    @property
    def memory_vector_enabled(self) -> bool:
        return bool(self._data["memory"]["vector"])

    @property
    def memory_relevance_threshold(self) -> float:
        return float(self._data["memory"]["relevance_threshold"])

    @property
    def memory_scoring(self) -> dict[str, int]:
        return dict(self._data["memory"]["scoring"])


    @property
    def skills_dir(self) -> Path:
        return Path(self._data.get("skills", {}).get("dir", "~/henk/skills")).expanduser()

    @property
    def skills_enabled(self) -> bool:
        return bool(self._data.get("skills", {}).get("enabled", True))

    @property
    def heartbeat_enabled(self) -> bool:
        return bool(self._data.get("heartbeat", {}).get("enabled", True))

    @property
    def heartbeat_interval(self) -> int:
        return int(self._data.get("heartbeat", {}).get("interval_seconds", 30))

    @property
    def raw(self) -> dict[str, Any]:
        return self._data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(data_dir: Path | None = None) -> Config:
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path(__file__).parent.parent / ".env")

    if data_dir is None:
        data_dir = Path.home() / "henk"

    config_path = data_dir / "henk.yaml"
    data = DEFAULT_CONFIG.copy()

    if config_path.exists():
        with open(config_path, encoding="utf-8") as file_handle:
            file_data = yaml.safe_load(file_handle)
        if file_data:
            data = _deep_merge(DEFAULT_CONFIG, file_data)

    return Config(data)
