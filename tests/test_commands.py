import io

from rich.console import Console

from henk.commands import dispatch_command, get_command_names
from henk.config import load_config


def _console_and_buffer():
    buffer = io.StringIO()
    return Console(file=buffer, force_terminal=False, color_system=None), buffer


def _tmp_config(tmp_path):
    config = load_config(tmp_path)
    config._data["paths"]["data_dir"] = str(tmp_path)
    config._data["paths"]["control_dir"] = str(tmp_path / "control")
    config._data["paths"]["logs_dir"] = str(tmp_path / "logs")
    config._data["paths"]["workspace_dir"] = str(tmp_path / "workspace")
    return config


def test_dispatch_help_prints_commands(tmp_path):
    config = _tmp_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, buffer = _console_and_buffer()

    dispatch_command("/help", config, console)
    assert "Beschikbare commands" in buffer.getvalue()


def test_dispatch_exit_returns_exit(tmp_path):
    config = _tmp_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, _ = _console_and_buffer()
    assert dispatch_command("/exit", config, console) == "exit"


def test_dispatch_stop_writes_hard_stop(tmp_path):
    config = _tmp_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, _ = _console_and_buffer()
    assert dispatch_command("/stop", config, console) == "exit"
    assert (config.control_dir / "hard_stop").read_text(encoding="utf-8") == "true"


def test_dispatch_pause_resume(tmp_path):
    config = _tmp_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, _ = _console_and_buffer()
    dispatch_command("/pause", config, console)
    assert (config.control_dir / "graceful_stop").read_text(encoding="utf-8") == "true"
    dispatch_command("/resume", config, console)
    assert (config.control_dir / "graceful_stop").read_text(encoding="utf-8") == "false"
    assert (config.control_dir / "hard_stop").read_text(encoding="utf-8") == "false"


def test_dispatch_unknown_command(tmp_path):
    config = _tmp_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, buffer = _console_and_buffer()
    dispatch_command("/onbekend", config, console)
    assert "Onbekend command" in buffer.getvalue()


def test_dispatch_model_updates_role_and_env(tmp_path):
    config = _tmp_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, _ = _console_and_buffer()
    env_path = tmp_path / ".env"
    answers = iter([
        "1",
        "1",
        "openai/gpt-4o",
        "deepseek/deepseek-chat",
        "2",
        "1",
        "anthropic-test-key",
        "0",
    ])

    dispatch_command(
        "/model",
        config,
        console,
        input_func=lambda prompt="": next(answers),
        env_path=env_path,
        config_path=tmp_path / "henk.yaml",
    )

    config_file = tmp_path / "henk.yaml"
    config_text = config_file.read_text(encoding="utf-8")
    assert "primary: openai/gpt-4o" in config_text
    assert "- deepseek/deepseek-chat" in config_text
    assert "ANTHROPIC_API_KEY=anthropic-test-key" in env_path.read_text(encoding="utf-8")


def test_get_command_names_contains_expected():
    commands = get_command_names()
    for expected in ["/help", "/exit", "/stop", "/status", "/history", "/model"]:
        assert expected in commands
