import subprocess
from pathlib import Path

import pytest

import install as installer


def _completed(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def _env(
    command: list[str] | None,
    version_text: str = "",
    *,
    version_ok: bool = False,
    pip_ok: bool = False,
) -> installer.PythonEnvironment:
    return installer.PythonEnvironment(
        command=command,
        version_text=version_text,
        version_ok=version_ok,
        pip_ok=pip_ok,
    )


def _configure_wizard(monkeypatch, tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    env_file = repo_dir / ".env"
    env_example = repo_dir / ".env.example"
    env_example.write_text("OPENAI_API_KEY=\n", encoding="utf-8")
    henk_dir = tmp_path / "henk"
    scripts_dir = tmp_path / "bin"
    scripts_dir.mkdir()

    monkeypatch.setattr(installer, "REPO_DIR", repo_dir)
    monkeypatch.setattr(installer, "ENV_FILE", env_file)
    monkeypatch.setattr(installer, "ENV_EXAMPLE", env_example)
    monkeypatch.setattr(installer, "HENK_DIR", henk_dir)
    monkeypatch.setattr(installer, "_user_scripts_dir", lambda: scripts_dir)
    monkeypatch.setattr(installer, "_ensure_terminal_command", lambda state, scripts_dir, print_func: None)
    return repo_dir, env_file, henk_dir, scripts_dir


def test_run_wizard_skips_bootstrap_when_python_ready(monkeypatch, tmp_path):
    _, env_file, _, scripts_dir = _configure_wizard(monkeypatch, tmp_path)
    commands: list[tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None):
        commands.append((command, cwd))
        return _completed(command)

    monkeypatch.setattr(installer, "_run_command", fake_run)
    monkeypatch.setattr(
        installer,
        "_detect_python_environment",
        lambda: _env(["python3"], "3.11", version_ok=True, pip_ok=True),
    )
    monkeypatch.setattr(installer, "_detect_package_manager", lambda: None)
    monkeypatch.setenv("PATH", "")

    state = installer.run_wizard(interactive=False, print_func=lambda *args, **kwargs: None)

    assert state.mode == "install"
    assert state.bootstrap_status == "not_needed"
    assert state.python_status == "ok"
    assert state.python_command == "python3"
    assert state.python_version == "3.11"
    assert state.package_status == "ok"
    assert state.config_status == "created"
    assert state.workspace_status == "created"
    assert state.path_ready is False
    assert env_file.exists()
    assert any(command == ["python3", "-m", "pip", "install", "--quiet", "--user", "-e", "."] for command, _ in commands)
    assert any(command == ["python3", "-m", "henk", "init"] for command, _ in commands)
    assert any("Scripts-dir staat mogelijk niet op PATH" in note for note in state.notes)
    assert scripts_dir.exists()


def test_bootstrap_declines_python_install_without_running_command(monkeypatch):
    state = installer.InstallState(platform="darwin", mode="install")
    commands: list[list[str]] = []

    monkeypatch.setattr(
        installer,
        "_detect_python_environment",
        lambda: _env(["python3"], "3.10", version_ok=False, pip_ok=True),
    )
    monkeypatch.setattr(
        installer,
        "_detect_package_manager",
        lambda: installer.PackageManager("brew", ["brew", "install", "python@3.11"], automatic=True),
    )
    monkeypatch.setattr(
        installer,
        "_run_command",
        lambda command, *, cwd=None: commands.append(command) or _completed(command),
    )

    with pytest.raises(installer.InstallError):
        installer._bootstrap_python(
            state,
            interactive=True,
            input_func=lambda prompt: "nee",
            print_func=lambda *args, **kwargs: None,
        )

    assert commands == []
    assert state.bootstrap_status == "declined"
    assert state.python_status == "error"
    assert state.package_manager == "brew"
    assert state.bootstrap_action == "brew install python@3.11"
    assert state.consent_requested is True
    assert state.consent_granted is False
    assert any("brew install python@3.11" in note for note in state.notes)


def test_bootstrap_runs_python_install_after_explicit_consent(monkeypatch):
    state = installer.InstallState(platform="darwin", mode="install")
    commands: list[list[str]] = []
    environments = iter(
        [
            _env(["python3"], "3.10", version_ok=False, pip_ok=True),
            _env(["python3"], "3.11", version_ok=True, pip_ok=True),
        ]
    )

    monkeypatch.setattr(installer, "_detect_python_environment", lambda: next(environments))
    monkeypatch.setattr(installer, "_current_process_python_ready", lambda: True)
    monkeypatch.setattr(
        installer,
        "_detect_package_manager",
        lambda: installer.PackageManager("brew", ["brew", "install", "python@3.11"], automatic=True),
    )

    def fake_run(command: list[str], *, cwd=None):
        commands.append(command)
        return _completed(command)

    monkeypatch.setattr(installer, "_run_command", fake_run)

    python_command = installer._bootstrap_python(
        state,
        interactive=True,
        input_func=lambda prompt: "ja",
        print_func=lambda *args, **kwargs: None,
    )

    assert python_command == ["python3"]
    assert commands == [["brew", "install", "python@3.11"]]
    assert state.bootstrap_status == "installed"
    assert state.python_status == "ok"
    assert state.package_manager == "brew"
    assert state.bootstrap_action == "brew install python@3.11"
    assert state.python_command == "python3"
    assert state.python_version == "3.11"
    assert state.consent_requested is True
    assert state.consent_granted is True


def test_detect_python_environment_prefers_working_homebrew_python(monkeypatch):
    command_outputs = {
        ("/opt/homebrew/bin/python3.11", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"): _completed(
            ["/opt/homebrew/bin/python3.11"],
            stdout="3.11\n",
        ),
        ("/opt/homebrew/bin/python3.11", "-m", "pip", "--version"): _completed(
            ["/opt/homebrew/bin/python3.11"],
            stdout="pip 24.0\n",
        ),
        ("python3", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"): _completed(
            ["python3"],
            stdout="3.9\n",
        ),
        ("python3", "-m", "pip", "--version"): _completed(["python3"], stdout="pip 21.0\n"),
        ("/usr/bin/python3", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"): _completed(
            ["/usr/bin/python3"],
            stdout="3.9\n",
        ),
        ("/usr/bin/python3", "-m", "pip", "--version"): _completed(["/usr/bin/python3"], stdout="pip 21.0\n"),
    }

    monkeypatch.setattr(installer.sys, "platform", "darwin")
    monkeypatch.setattr(installer.sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(installer, "_homebrew_python_candidates", lambda: [["/opt/homebrew/bin/python3.11"]])
    monkeypatch.setattr(installer, "_run_command", lambda command, *, cwd=None: command_outputs.get(tuple(command), _completed(command, returncode=1)))

    env = installer._detect_python_environment()

    assert env.command == ["/opt/homebrew/bin/python3.11"]
    assert env.version_text == "3.11"
    assert env.version_ok is True
    assert env.pip_ok is True


def test_bootstrap_restarts_installer_with_new_python(monkeypatch):
    class RestartCalled(Exception):
        pass

    state = installer.InstallState(platform="darwin", mode="install")
    commands: list[list[str]] = []
    restart_commands: list[list[str]] = []
    environments = iter(
        [
            _env(["python3"], "3.10", version_ok=False, pip_ok=True),
            _env(["/opt/homebrew/bin/python3.11"], "3.11", version_ok=True, pip_ok=True),
        ]
    )

    monkeypatch.setattr(installer, "_detect_python_environment", lambda: next(environments))
    monkeypatch.setattr(installer, "_current_process_python_ready", lambda: False)
    monkeypatch.setattr(
        installer,
        "_detect_package_manager",
        lambda: installer.PackageManager("brew", ["brew", "install", "python@3.11"], automatic=True),
    )
    monkeypatch.setattr(
        installer,
        "_run_command",
        lambda command, *, cwd=None: commands.append(command) or _completed(command),
    )

    def fake_restart(command: list[str]) -> None:
        restart_commands.append(command)
        raise RestartCalled()

    monkeypatch.setattr(installer, "_restart_with_python", fake_restart)

    with pytest.raises(RestartCalled):
        installer._bootstrap_python(
            state,
            interactive=True,
            input_func=lambda prompt: "ja",
            print_func=lambda *args, **kwargs: None,
        )

    assert commands == [["brew", "install", "python@3.11"]]
    assert restart_commands == [["/opt/homebrew/bin/python3.11"]]
    assert state.bootstrap_status == "installed"
    assert state.python_status == "ok"
    assert state.python_command == "/opt/homebrew/bin/python3.11"
    assert state.bootstrap_interpreter == "/opt/homebrew/bin/python3.11"
    assert state.restart_status == "restarting"


def test_bootstrap_reports_manual_rerun_when_restart_fails(monkeypatch):
    state = installer.InstallState(platform="darwin", mode="install")
    environments = iter(
        [
            _env(["python3"], "3.10", version_ok=False, pip_ok=True),
            _env(["/opt/homebrew/bin/python3.11"], "3.11", version_ok=True, pip_ok=True),
        ]
    )

    monkeypatch.setattr(installer, "_detect_python_environment", lambda: next(environments))
    monkeypatch.setattr(installer, "_current_process_python_ready", lambda: False)
    monkeypatch.setattr(
        installer,
        "_detect_package_manager",
        lambda: installer.PackageManager("brew", ["brew", "install", "python@3.11"], automatic=True),
    )
    monkeypatch.setattr(installer, "_run_command", lambda command, *, cwd=None: _completed(command))
    monkeypatch.setattr(installer, "_restart_with_python", lambda command: (_ for _ in ()).throw(OSError("kaboom")))

    with pytest.raises(
        installer.InstallError,
        match=r"Voer handmatig uit: /opt/homebrew/bin/python3.11 .*install.py",
    ):
        installer._bootstrap_python(
            state,
            interactive=True,
            input_func=lambda prompt: "ja",
            print_func=lambda *args, **kwargs: None,
        )

    assert state.bootstrap_status == "installed"
    assert state.restart_status == "failed"


def test_ensure_posix_path_configuration_updates_profiles(monkeypatch, tmp_path):
    profile = tmp_path / ".zshrc"
    profile.write_text("# bestaand\n", encoding="utf-8")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setattr(installer.sys, "platform", "darwin")

    changed = installer._ensure_posix_path_configuration(tmp_path / "bin", [profile])

    assert changed is True
    content = profile.read_text(encoding="utf-8")
    assert installer.PATH_BLOCK_START in content
    assert 'export PATH="' in content
    assert str(tmp_path / "bin") in content


def test_ensure_posix_henk_launcher_creates_uppercase_wrapper(monkeypatch, tmp_path):
    scripts_dir = tmp_path / "bin"
    scripts_dir.mkdir()
    launcher = scripts_dir / "henk"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    monkeypatch.setattr(installer.sys, "platform", "linux")

    created = installer._ensure_posix_henk_launcher(scripts_dir)

    assert (scripts_dir / "Henk").exists()
    if created:
        assert (scripts_dir / "Henk") != launcher


def test_bootstrap_requires_manual_instructions_without_package_manager(monkeypatch):
    state = installer.InstallState(platform="linux", mode="install")

    monkeypatch.setattr(installer, "_detect_python_environment", lambda: _env(None))
    monkeypatch.setattr(installer, "_detect_package_manager", lambda: None)
    monkeypatch.setattr(installer.sys, "platform", "linux")

    with pytest.raises(installer.InstallError, match="Python 3.11\\+ ontbreekt"):
        installer._bootstrap_python(
            state,
            interactive=True,
            input_func=lambda prompt: "ja",
            print_func=lambda *args, **kwargs: None,
        )

    assert state.bootstrap_status == "manual_required"
    assert state.python_status == "error"
    assert state.package_manager == ""
    assert state.bootstrap_action == ""
    assert state.consent_requested is False
    assert state.consent_granted is False
    assert any("Installeer Python 3.11+" in note for note in state.notes)


def test_bootstrap_treats_broken_pip_as_bootstrap_problem(monkeypatch):
    state = installer.InstallState(platform="darwin", mode="install")

    monkeypatch.setattr(
        installer,
        "_detect_python_environment",
        lambda: _env(["python3"], "3.11", version_ok=True, pip_ok=False),
    )
    monkeypatch.setattr(
        installer,
        "_detect_package_manager",
        lambda: installer.PackageManager("brew", ["brew", "install", "python@3.11"], automatic=True),
    )

    with pytest.raises(installer.InstallError, match="Voer dit handmatig uit: brew install python@3.11"):
        installer._bootstrap_python(
            state,
            interactive=False,
            input_func=lambda prompt: "ja",
            print_func=lambda *args, **kwargs: None,
        )

    assert state.bootstrap_status == "manual_required"
    assert state.python_status == "error"
    assert state.package_manager == "brew"
    assert state.bootstrap_action == "brew install python@3.11"
    assert state.consent_requested is True
    assert state.consent_granted is False
    assert any("Voer dit handmatig uit: brew install python@3.11" in note for note in state.notes)


def test_detect_package_manager_prefers_brew_on_macos(monkeypatch):
    monkeypatch.setattr(installer.sys, "platform", "darwin")
    monkeypatch.setattr(installer.shutil, "which", lambda name: "/opt/homebrew/bin/brew" if name == "brew" else None)

    manager = installer._detect_package_manager()

    assert manager is not None
    assert manager.name == "brew"
    assert manager.install_command == ["brew", "install", "python@3.11"]
    assert manager.automatic is True


def test_detect_package_manager_prefers_winget_on_windows(monkeypatch):
    monkeypatch.setattr(installer.sys, "platform", "win32")
    monkeypatch.setattr(installer.shutil, "which", lambda name: "C:/Windows/System32/winget.exe" if name == "winget" else None)

    manager = installer._detect_package_manager()

    assert manager is not None
    assert manager.name == "winget"
    assert manager.install_command == ["winget", "install", "Python.Python.3.11"]
    assert manager.automatic is True


def test_install_wrapper_remains_thin():
    repo_dir = Path(__file__).resolve().parents[1]
    pyproject = (repo_dir / "pyproject.toml").read_text(encoding="utf-8")
    install_wrapper = (repo_dir / "installeer.sh").read_text(encoding="utf-8")
    deinstall_wrapper = (repo_dir / "deinstalleer.sh").read_text(encoding="utf-8")
    mac_install_command = (repo_dir / "Henk Installeren.command").read_text(encoding="utf-8")
    mac_uninstall_command = (repo_dir / "Henk Deinstalleren.command").read_text(encoding="utf-8")
    desktop_entry = (repo_dir / "Henk Installeren.desktop").read_text(encoding="utf-8")
    uninstall_desktop_entry = (repo_dir / "Henk Deinstalleren.desktop").read_text(encoding="utf-8")
    win_install_bat = (repo_dir / "Henk Installeren.bat").read_text(encoding="utf-8")
    win_deinstall_bat = (repo_dir / "Henk Deinstalleren.bat").read_text(encoding="utf-8")

    assert "[tool.setuptools.packages.find]" in pyproject
    assert 'include = ["henk*"]' in pyproject
    assert 'exclude = ["skills*", "tests*"]' in pyproject
    # installeer.sh thin wrapper
    assert "install.py" in install_wrapper
    assert "brew install" not in install_wrapper
    assert "winget install" not in install_wrapper
    assert "pip install" not in install_wrapper
    # deinstalleer.sh thin wrapper
    assert "deinstalleer.py" in deinstall_wrapper
    assert len(deinstall_wrapper.splitlines()) < 20
    assert "rm -rf" not in deinstall_wrapper
    assert "pip uninstall" not in deinstall_wrapper
    # macOS install command
    assert "python3 install.py" in mac_install_command
    assert "HENK_SKIP_INTERNAL_PAUSE=1" in mac_install_command
    assert 'read -rp "Druk op Enter om dit venster te sluiten..."' in mac_install_command
    assert "brew install" not in mac_install_command
    assert "pip install" not in mac_install_command
    # macOS deinstall command
    assert "deinstalleer.py" in mac_uninstall_command
    assert "HENK_SKIP_INTERNAL_PAUSE=1" in mac_uninstall_command
    assert "rm -rf" not in mac_uninstall_command
    # Desktop entries
    assert "/home/user" not in desktop_entry
    assert "/home/user" not in uninstall_desktop_entry
    # Windows .bat launchers
    assert "install.py" in win_install_bat
    assert "deinstalleer.py" in win_deinstall_bat
    assert len(win_install_bat.splitlines()) < 10
    assert len(win_deinstall_bat.splitlines()) < 10
