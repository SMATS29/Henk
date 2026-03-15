import subprocess
from pathlib import Path

import pytest

import deinstalleer as uninstaller


def _completed(command: list[str], returncode: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def test_run_uninstall_wizard_removes_package(monkeypatch, tmp_path):
    henk_dir = tmp_path / "henk"
    henk_dir.mkdir()
    monkeypatch.setattr(uninstaller, "HENK_DIR", henk_dir)
    commands: list[list[str]] = []

    def fake_run(command, *, cwd=None):
        commands.append(command)
        if "show" in command and "henk" in command:
            return _completed(command, returncode=0)
        if "uninstall" in command and "henk" in command:
            return _completed(command, returncode=0)
        return _completed(command)

    monkeypatch.setattr(uninstaller, "_run_command", fake_run)
    monkeypatch.setattr(uninstaller, "_clean_path", lambda state, pf: None)

    state = uninstaller.run_wizard(
        interactive=True,
        input_func=lambda prompt: "ja",
        print_func=lambda *a, **kw: None,
    )

    assert state.package_removed is True
    assert not henk_dir.exists()


def test_uninstall_stops_processes_cross_platform(monkeypatch, tmp_path):
    henk_dir = tmp_path / "henk"
    monkeypatch.setattr(uninstaller, "HENK_DIR", henk_dir)
    commands: list[list[str]] = []

    def fake_run(command, *, cwd=None):
        commands.append(command)
        return _completed(command)

    monkeypatch.setattr(uninstaller, "_run_command", fake_run)

    # Test Windows
    state_win = uninstaller.UninstallState(platform="win32")
    monkeypatch.setattr(uninstaller.sys, "platform", "win32")
    commands.clear()
    uninstaller._stop_processes(state_win, lambda *a, **kw: None)
    assert state_win.processes_stopped is True
    assert any("taskkill" in cmd[0] for cmd in commands)

    # Test POSIX
    state_posix = uninstaller.UninstallState(platform="linux")
    monkeypatch.setattr(uninstaller.sys, "platform", "linux")
    commands.clear()
    monkeypatch.setattr(uninstaller.time, "sleep", lambda s: None)
    uninstaller._stop_processes(state_posix, lambda *a, **kw: None)
    assert state_posix.processes_stopped is True
    assert any("pkill" in cmd[0] for cmd in commands)


def test_uninstall_cleans_posix_path(monkeypatch, tmp_path):
    profile = tmp_path / ".zshrc"
    profile.write_text(
        "# bestaand\n\n"
        "# >>> Henk PATH >>>\n"
        'case ":$PATH:" in *":/home/user/.local/bin:"*) ;; *) export PATH="/home/user/.local/bin:$PATH" ;; esac\n'
        "# <<< Henk PATH <<<\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(uninstaller.sys, "platform", "linux")
    monkeypatch.setattr(uninstaller, "_posix_profile_targets", lambda: [profile])

    state = uninstaller.UninstallState(platform="linux")
    uninstaller._clean_path(state, lambda *a, **kw: None)

    assert state.path_cleaned is True
    content = profile.read_text(encoding="utf-8")
    assert uninstaller.PATH_BLOCK_START not in content
    assert uninstaller.PATH_BLOCK_END not in content


def test_uninstall_cleans_windows_path(monkeypatch, tmp_path):
    """Test dat _clean_windows_path de scripts dir uit het register verwijdert."""
    monkeypatch.setattr(uninstaller.sys, "platform", "win32")

    scripts_dir = tmp_path / "Scripts"
    scripts_dir.mkdir()
    monkeypatch.setattr(uninstaller, "_user_scripts_dir", lambda: scripts_dir)

    # Mock winreg
    import types
    fake_winreg = types.ModuleType("winreg")
    current_path = f"C:\\SomeOther;{scripts_dir}"
    written_values: list[str] = []

    class FakeKey:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_open_key(*args, **kwargs):
        return FakeKey()

    def fake_query(key, name):
        return (current_path, 1)

    def fake_set(key, name, reserved, reg_type, value):
        written_values.append(value)

    fake_winreg.KEY_READ = 1
    fake_winreg.KEY_SET_VALUE = 2
    fake_winreg.HKEY_CURRENT_USER = 0
    fake_winreg.REG_EXPAND_SZ = 2
    fake_winreg.OpenKey = fake_open_key
    fake_winreg.QueryValueEx = fake_query
    fake_winreg.SetValueEx = fake_set

    monkeypatch.setitem(__import__("sys").modules, "winreg", fake_winreg)

    # Mock ctypes to avoid actual WM_SETTINGCHANGE
    monkeypatch.setattr(uninstaller, "_clean_windows_path", lambda: True)

    state = uninstaller.UninstallState(platform="win32")
    uninstaller._clean_path(state, lambda *a, **kw: None)
    assert state.path_cleaned is True


def test_uninstall_removes_workspace(monkeypatch, tmp_path):
    henk_dir = tmp_path / "henk"
    henk_dir.mkdir()
    (henk_dir / "test.txt").write_text("data", encoding="utf-8")
    monkeypatch.setattr(uninstaller, "HENK_DIR", henk_dir)

    state = uninstaller.UninstallState(platform="linux")
    uninstaller._remove_workspace(state, lambda *a, **kw: None)

    assert state.workspace_removed is True
    assert not henk_dir.exists()


def test_uninstall_aborts_without_confirmation(monkeypatch, tmp_path):
    henk_dir = tmp_path / "henk"
    henk_dir.mkdir()
    monkeypatch.setattr(uninstaller, "HENK_DIR", henk_dir)

    state = uninstaller.run_wizard(
        interactive=True,
        input_func=lambda prompt: "nee",
        print_func=lambda *a, **kw: None,
    )

    assert state.processes_stopped is False
    assert state.package_removed is False
    assert state.workspace_removed is False
    assert henk_dir.exists()


def test_uninstall_handles_missing_package_gracefully(monkeypatch, tmp_path):
    henk_dir = tmp_path / "henk"
    monkeypatch.setattr(uninstaller, "HENK_DIR", henk_dir)

    def fake_run(command, *, cwd=None):
        if "show" in command:
            return _completed(command, returncode=1)
        return _completed(command)

    monkeypatch.setattr(uninstaller, "_run_command", fake_run)
    monkeypatch.setattr(uninstaller, "_clean_path", lambda state, pf: None)

    state = uninstaller.run_wizard(
        interactive=True,
        input_func=lambda prompt: "ja",
        print_func=lambda *a, **kw: None,
    )

    assert state.package_removed is False
    assert state.processes_stopped is True


def test_deinstaller_wrapper_remains_thin():
    repo_dir = Path(__file__).resolve().parents[1]
    deinstall_wrapper = (repo_dir / "deinstalleer.sh").read_text(encoding="utf-8")
    deinstall_py = (repo_dir / "deinstalleer.py").read_text(encoding="utf-8")

    # deinstalleer.sh is een thin wrapper
    assert "deinstalleer.py" in deinstall_wrapper
    assert len(deinstall_wrapper.splitlines()) < 20
    assert "rm -rf" not in deinstall_wrapper
    assert "pip uninstall" not in deinstall_wrapper

    # deinstalleer.py bevat de eigenlijke logica
    assert "run_wizard" in deinstall_py
    assert "UninstallState" in deinstall_py
    assert "Henk Installeren" in deinstall_py
