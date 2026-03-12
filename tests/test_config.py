"""Tests voor config laden."""

from henk.config import Config, DEFAULT_CONFIG, _deep_merge, load_config


def test_default_config_has_required_fields():
    """Default config bevat alle verplichte velden."""
    config = Config(DEFAULT_CONFIG)
    assert config.model == "claude-sonnet-4-6"
    assert config.provider == "anthropic"
    assert config.api_key_env_var == "ANTHROPIC_API_KEY"
    assert config.max_tool_calls == 4
    assert config.memory_vector_enabled is True
    assert config.memory_relevance_threshold == 0.3
    assert config.memory_scoring["initial_score"] == 50


def test_deep_merge():
    """Deep merge overschrijft nested waarden correct."""
    base = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 10}, "e": 5}
    result = _deep_merge(base, override)
    assert result == {"a": {"b": 10, "c": 2}, "d": 3, "e": 5}


def test_load_config_with_yaml(tmp_path):
    """Config laden vanuit een henk.yaml bestand."""
    data_dir = tmp_path / "henk"
    data_dir.mkdir()
    config_file = data_dir / "henk.yaml"
    config_file.write_text(
        "provider:\n  model: claude-sonnet-4-6\n",
        encoding="utf-8",
    )

    config = load_config(data_dir)
    assert config.model == "claude-sonnet-4-6"
    assert config.provider == "anthropic"


def test_load_config_uses_provider_for_api_key_env_var(tmp_path):
    """De env var naam volgt de actieve provider."""
    data_dir = tmp_path / "henk"
    data_dir.mkdir()
    config_file = data_dir / "henk.yaml"
    config_file.write_text(
        "provider:\n  default: anthropic\n  model: claude-sonnet-4-6\n",
        encoding="utf-8",
    )

    config = load_config(data_dir)
    assert config.provider == "anthropic"
    assert config.api_key_env_var == "ANTHROPIC_API_KEY"
