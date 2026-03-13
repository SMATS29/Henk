"""Tests voor config laden."""

from henk.config import Config, DEFAULT_CONFIG, _deep_merge, load_config


def test_default_config_has_required_fields():
    config = Config(DEFAULT_CONFIG)
    assert "anthropic" in config.providers_config
    assert "default" in config.roles_config
    assert config.max_tool_calls == 4
    assert config.memory_vector_enabled is True


def test_deep_merge():
    base = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 10}, "e": 5}
    result = _deep_merge(base, override)
    assert result == {"a": {"b": 10, "c": 2}, "d": 3, "e": 5}


def test_load_config_with_yaml(tmp_path):
    data_dir = tmp_path / "henk"
    data_dir.mkdir()
    config_file = data_dir / "henk.yaml"
    config_file.write_text(
        "roles:\n  default:\n    primary: openai/gpt-4o\n",
        encoding="utf-8",
    )

    config = load_config(data_dir)
    assert config.roles_config["default"]["primary"] == "openai/gpt-4o"
