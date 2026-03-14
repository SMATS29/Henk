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
    install_wrapper = (repo_dir / "installeer.sh").read_text(encoding="utf-8")
    mac_install_command = (repo_dir / "Henk Installeren.command").read_text(encoding="utf-8")
    mac_uninstall_command = (repo_dir / "Henk Deinstalleren.command").read_text(encoding="utf-8")
    desktop_entry = (repo_dir / "Henk Installeren.desktop").read_text(encoding="utf-8")
    uninstall_desktop_entry = (repo_dir / "Henk Deinstalleren.desktop").read_text(encoding="utf-8")

    assert "install.py" in install_wrapper
    assert "brew install" not in install_wrapper
    assert "winget install" not in install_wrapper
    assert "pip install" not in install_wrapper
    assert "python3 install.py" in mac_install_command
    assert "HENK_SKIP_INTERNAL_PAUSE=1" in mac_install_command
    assert 'read -rp "Druk op Enter om dit venster te sluiten..."' in mac_install_command
    assert "brew install" not in mac_install_command
    assert "pip install" not in mac_install_command
    assert "bash deinstalleer.sh" in mac_uninstall_command
    assert "rm -rf" not in mac_uninstall_command
    assert "/home/user" not in desktop_entry
    assert "/home/user" not in uninstall_desktop_entry


def test_deinstaller_mentions_mac_clickable_installer():
    repo_dir = Path(__file__).resolve().parents[1]
    deinstaller = (repo_dir / "deinstalleer.sh").read_text(encoding="utf-8")

    assert "Henk Installeren.command" in deinstaller
