import io

from rich.console import Console

from henk.commands import dispatch_command, get_command_names
from henk.config import load_config


def _console_and_buffer():
    buffer = io.StringIO()
    return Console(file=buffer, force_terminal=False, color_system=None), buffer


def test_dispatch_help_prints_commands(tmp_path):
    config = load_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, buffer = _console_and_buffer()

    dispatch_command("/help", config, console)
    assert "Beschikbare commands" in buffer.getvalue()


def test_dispatch_exit_returns_exit(tmp_path):
    config = load_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, _ = _console_and_buffer()
    assert dispatch_command("/exit", config, console) == "exit"


def test_dispatch_stop_writes_hard_stop(tmp_path):
    config = load_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, _ = _console_and_buffer()
    assert dispatch_command("/stop", config, console) == "exit"
    assert (config.control_dir / "hard_stop").read_text(encoding="utf-8") == "true"


def test_dispatch_pause_resume(tmp_path):
    config = load_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, _ = _console_and_buffer()
    dispatch_command("/pause", config, console)
    assert (config.control_dir / "graceful_stop").read_text(encoding="utf-8") == "true"
    dispatch_command("/resume", config, console)
    assert (config.control_dir / "graceful_stop").read_text(encoding="utf-8") == "false"
    assert (config.control_dir / "hard_stop").read_text(encoding="utf-8") == "false"


def test_dispatch_unknown_command(tmp_path):
    config = load_config(tmp_path)
    config.control_dir.mkdir(parents=True, exist_ok=True)
    console, buffer = _console_and_buffer()
    dispatch_command("/onbekend", config, console)
    assert "Onbekend command" in buffer.getvalue()


def test_get_command_names_contains_expected():
    commands = get_command_names()
    for expected in ["/help", "/exit", "/stop", "/status", "/history"]:
        assert expected in commands
