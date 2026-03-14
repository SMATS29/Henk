#!/usr/bin/env python3
"""Cross-platform install wizard voor Henk.

Gebruik:
    python install.py
    python3 install.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO_DIR = Path(__file__).parent.resolve()
HENK_DIR = Path.home() / "henk"
ENV_FILE = REPO_DIR / ".env"
ENV_EXAMPLE = REPO_DIR / ".env.example"


class InstallError(RuntimeError):
    """Afbreekfout voor installatiestappen."""


@dataclass
class InstallState:
    platform: str
    mode: str
    python_version: str = ""
    python_command: str = ""
    scripts_dir: str = ""
    path_ready: bool = False
    bootstrap_status: str = "pending"
    package_manager: str = ""
    bootstrap_action: str = ""
    bootstrap_interpreter: str = ""
    consent_requested: bool = False
    consent_granted: bool = False
    restart_status: str = "not_needed"
    python_status: str = "pending"
    package_status: str = "pending"
    config_status: str = "pending"
    workspace_status: str = "pending"
    launcher_status: str = "wizard_primary"
    notes: list[str] = field(default_factory=list)


@dataclass
class PythonEnvironment:
    command: list[str] | None
    version_text: str = ""
    version_ok: bool = False
    pip_ok: bool = False


@dataclass
class PackageManager:
    name: str
    install_command: list[str] | None
    automatic: bool


PATH_BLOCK_START = "# >>> Henk PATH >>>"
PATH_BLOCK_END = "# <<< Henk PATH <<<"


def _run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, cwd=str(cwd) if cwd else None)


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _pause(interactive: bool, input_func: Callable[[str], str]) -> None:
    if interactive and os.environ.get("HENK_SKIP_INTERNAL_PAUSE") != "1":
        input_func("Druk op Enter om dit venster te sluiten...")


def _print_header(print_func: Callable[..., None]) -> None:
    print_func("=" * 46)
    print_func("   HENK - Installatie Wizard")
    print_func("=" * 46)
    print_func()


def _user_scripts_dir() -> Path:
    if sys.platform == "win32":
        return Path(sysconfig.get_path("scripts", "nt_user"))
    return Path(sysconfig.get_path("scripts", "posix_user"))


def _scripts_dir_for_install(python_command: list[str], *, user_install: bool) -> Path:
    if user_install:
        scheme = "nt_user" if sys.platform == "win32" else "posix_user"
        code = f"import sysconfig; print(sysconfig.get_path('scripts', '{scheme}'))"
    else:
        code = "import sysconfig; print(sysconfig.get_path('scripts'))"

    result = _run_command(python_command + ["-c", code])
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return _user_scripts_dir()


def _current_process_python_ready() -> bool:
    if sys.version_info < (3, 11):
        return False

    pip_result = _run_command([sys.executable, "-m", "pip", "--version"])
    return pip_result.returncode == 0


def _homebrew_python_candidates() -> list[list[str]]:
    if sys.platform != "darwin":
        return []

    candidates: list[list[str]] = []
    brew_prefix = shutil.which("brew")
    if brew_prefix:
        prefix_result = _run_command(["brew", "--prefix", "python@3.11"])
        if prefix_result.returncode == 0:
            prefix = prefix_result.stdout.strip()
            if prefix:
                candidates.append([str(Path(prefix) / "bin" / "python3.11")])

    candidates.extend([
        ["/opt/homebrew/bin/python3.11"],
        ["/usr/local/bin/python3.11"],
        ["/opt/homebrew/opt/python@3.11/bin/python3.11"],
        ["/usr/local/opt/python@3.11/bin/python3.11"],
    ])
    return candidates


def _candidate_sort_key(env: PythonEnvironment) -> tuple[int, int, int, int]:
    try:
        major_text, minor_text = env.version_text.split(".", 1)
        major, minor = int(major_text), int(minor_text)
    except ValueError:
        major, minor = 0, 0

    usability = 2 if env.version_ok and env.pip_ok else 1 if env.version_ok else 0
    return (usability, major, minor, 1 if env.pip_ok else 0)


def _path_ready(scripts_dir: Path) -> bool:
    normalized_scripts_dir = os.path.normcase(str(scripts_dir.expanduser()))
    path_entries = [os.path.normcase(str(Path(part).expanduser())) for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    return normalized_scripts_dir in path_entries


def _upsert_text_block(path: Path, start_marker: str, end_marker: str, body: str) -> bool:
    block = f"{start_marker}\n{body}\n{end_marker}"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    else:
        existing = ""

    if start_marker in existing and end_marker in existing:
        before, _, remainder = existing.partition(start_marker)
        _, _, after = remainder.partition(end_marker)
        new_content = f"{before}{block}{after}"
    else:
        prefix = existing.rstrip()
        new_content = f"{prefix}\n\n{block}\n" if prefix else f"{block}\n"

    if new_content == existing:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_content, encoding="utf-8")
    return True


def _posix_profile_targets() -> list[Path]:
    home = Path.home()
    shell_name = Path(os.environ.get("SHELL", "")).name
    targets = [home / ".profile"]

    if shell_name == "fish":
        targets = [home / ".config" / "fish" / "config.fish"]
    elif shell_name == "zsh" or sys.platform == "darwin":
        targets.extend([home / ".zprofile", home / ".zshrc"])
    elif shell_name == "bash":
        targets.extend([home / ".bash_profile", home / ".bashrc"])
    else:
        targets.append(home / ".bashrc")

    unique_targets: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        if target not in seen:
            unique_targets.append(target)
            seen.add(target)
    return unique_targets


def _ensure_posix_path_configuration(scripts_dir: Path, targets: list[Path]) -> bool:
    shell_name = Path(os.environ.get("SHELL", "")).name
    is_fish = shell_name == "fish"
    scripts_dir_text = str(scripts_dir.expanduser())

    if is_fish:
        body = "\n".join([
            f'if not contains -- "{scripts_dir_text}" $PATH',
            f'    set -gx PATH "{scripts_dir_text}" $PATH',
            "end",
        ])
    else:
        body = "\n".join([
            f'case ":$PATH:" in *":{scripts_dir_text}:"*) ;; *) export PATH="{scripts_dir_text}:$PATH" ;; esac',
        ])

    changed = False
    for target in targets:
        changed = _upsert_text_block(target, PATH_BLOCK_START, PATH_BLOCK_END, body) or changed
    return changed


def _ensure_posix_henk_launcher(scripts_dir: Path) -> bool:
    if sys.platform == "win32":
        return False

    lower_launcher = scripts_dir / "henk"
    upper_launcher = scripts_dir / "Henk"
    if not lower_launcher.exists() or upper_launcher.exists():
        return False

    try:
        upper_launcher.symlink_to(lower_launcher.name)
    except OSError:
        upper_launcher.write_text(f'#!/bin/sh\nexec "{lower_launcher}" "$@"\n', encoding="utf-8")
        mode = lower_launcher.stat().st_mode if lower_launcher.exists() else 0o755
        upper_launcher.chmod(mode | 0o111)
    return True


def _ensure_windows_path_configuration(scripts_dir: Path) -> bool:
    if sys.platform != "win32":
        return False

    import winreg

    scripts_dir_text = str(scripts_dir.expanduser())
    access = winreg.KEY_READ | winreg.KEY_SET_VALUE
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, access) as key:
        try:
            current_value, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_value = ""

        entries = [entry for entry in current_value.split(os.pathsep) if entry]
        normalized_entries = {os.path.normcase(entry) for entry in entries}
        if os.path.normcase(scripts_dir_text) in normalized_entries:
            return False

        entries.append(scripts_dir_text)
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, os.pathsep.join(entries))

    try:
        import ctypes

        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            5000,
            None,
        )
    except OSError:
        pass

    return True


def _ensure_terminal_command(state: InstallState, scripts_dir: Path, print_func: Callable[..., None]) -> None:
    print_func("[ 5/7 ] Terminal-commando beschikbaar maken...")

    launcher_created = _ensure_posix_henk_launcher(scripts_dir)
    path_is_ready = _path_ready(scripts_dir)
    state.scripts_dir = str(scripts_dir)
    state.path_ready = path_is_ready

    if sys.platform == "win32":
        changed = False if path_is_ready else _ensure_windows_path_configuration(scripts_dir)
        state.launcher_status = "ready" if path_is_ready else "configured" if changed else "manual_path"
    else:
        changed = False if path_is_ready else _ensure_posix_path_configuration(scripts_dir, _posix_profile_targets())
        state.launcher_status = "ready" if path_is_ready else "configured" if changed else "manual_path"

    if launcher_created:
        state.notes.append(f"Extra launcher aangemaakt: {scripts_dir / 'Henk'}")

    if state.launcher_status == "ready":
        print_func("  Commando staat al op PATH. OK\n")
        return

    if state.launcher_status == "configured":
        state.notes.append("Open een nieuwe terminal en start Henk met: henk")
        print_func("  PATH is ingesteld voor nieuwe terminalvensters. OK\n")
        return

    state.notes.append(f"Voeg deze map toe aan PATH: {scripts_dir}")
    print_func(f"  PATH kon niet automatisch worden ingesteld. Voeg dit pad toe: {scripts_dir}\n")



def _choose_mode(interactive: bool, input_func: Callable[[str], str], print_func: Callable[..., None]) -> str:
    default = "update" if HENK_DIR.exists() else "install"
    if not interactive:
        return default

    print_func("Wat wil je doen?")
    if HENK_DIR.exists():
        print_func("  1. Bijwerken (aanbevolen)")
        print_func("  2. Herstellen")
        print_func("  0. Stoppen")
        choice = input_func("Kies een optie [1]: ").strip() or "1"
        if choice == "2":
            return "repair"
        if choice == "0":
            return "cancel"
        return "update"

    print_func("  1. Installeren (aanbevolen)")
    print_func("  0. Stoppen")
    choice = input_func("Kies een optie [1]: ").strip() or "1"
    if choice == "0":
        return "cancel"
    return "install"


def _stop_henk(print_func: Callable[..., None]) -> None:
    print_func("[ 1/7 ] Actieve Henk-processen stoppen...")
    if sys.platform == "win32":
        _run_command(["taskkill", "/F", "/FI", "IMAGENAME eq henk.exe"])
        _run_command(["taskkill", "/F", "/FI", "WINDOWTITLE eq henk*"])
    else:
        _run_command(["pkill", "-TERM", "-f", "python.*henk"])
        _run_command(["pkill", "-TERM", "-f", "[/]henk$"])
    print_func("  Klaar. OK\n")


def _detect_python_environment() -> PythonEnvironment:
    candidates: list[list[str]] = []
    if sys.platform == "win32":
        candidates.extend([["py", "-3"], ["python"], ["python3"]])
    else:
        candidates.extend(_homebrew_python_candidates())
        candidates.extend([["python3"], ["python"]])
    if sys.executable:
        candidates.append([sys.executable])

    seen: set[str] = set()
    best_env = PythonEnvironment(command=None)
    best_score = (-1, -1, -1, -1)
    for command in candidates:
        display = " ".join(command)
        if display in seen:
            continue
        seen.add(display)

        version_result = _run_command(command + ["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"])
        if version_result.returncode != 0:
            continue

        version_text = (version_result.stdout or "").strip()
        try:
            major_text, minor_text = version_text.split(".", 1)
            major, minor = int(major_text), int(minor_text)
        except ValueError:
            continue

        pip_result = _run_command(command + ["-m", "pip", "--version"])
        env = PythonEnvironment(
            command=command,
            version_text=version_text,
            version_ok=major > 3 or (major == 3 and minor >= 11),
            pip_ok=pip_result.returncode == 0,
        )
        score = _candidate_sort_key(env)
        if score > best_score:
            best_env = env
            best_score = score
        if env.version_ok and env.pip_ok:
            return env

    return best_env


def _detect_package_manager() -> PackageManager | None:
    if sys.platform == "darwin":
        return PackageManager("brew", ["brew", "install", "python@3.11"], automatic=True) if shutil.which("brew") else None
    if sys.platform == "win32":
        return (
            PackageManager("winget", ["winget", "install", "Python.Python.3.11"], automatic=True)
            if shutil.which("winget")
            else None
        )

    for name in ("apt", "dnf", "yum", "pacman"):
        if shutil.which(name):
            return PackageManager(name, None, automatic=False)
    return None


def _manual_python_instructions(manager: PackageManager | None) -> str:
    if sys.platform == "darwin":
        if manager and manager.name == "brew":
            return "Installeer Python 3.11+ handmatig met: brew install python@3.11"
        return "Installeer Homebrew vanaf https://brew.sh en voer daarna uit: brew install python@3.11, of installeer Python via https://python.org"
    if sys.platform == "win32":
        if manager and manager.name == "winget":
            return "Installeer Python 3.11+ handmatig met: winget install Python.Python.3.11"
        return "Installeer Python 3.11+ via https://python.org of gebruik winget."

    if manager and manager.name == "apt":
        return "Installeer Python 3.11+ handmatig met apt, bijvoorbeeld via je distro repositories."
    if manager and manager.name == "dnf":
        return "Installeer Python 3.11+ handmatig met dnf, bijvoorbeeld via je distro repositories."
    if manager and manager.name == "yum":
        return "Installeer Python 3.11+ handmatig met yum, bijvoorbeeld via je distro repositories."
    if manager and manager.name == "pacman":
        return "Installeer Python 3.11+ handmatig met pacman, bijvoorbeeld via je distro repositories."
    return "Installeer Python 3.11+ via de package manager van je Linux-distributie."


def _python_problem(env: PythonEnvironment) -> str:
    if env.command is None:
        return "Python 3.11+ ontbreekt"
    if not env.version_ok:
        return f"Python {env.version_text} is te oud"
    if not env.pip_ok:
        return f"pip ontbreekt of werkt niet voor {' '.join(env.command)}"
    return ""


def _restart_with_python(command: list[str]) -> None:
    if os.environ.get("HENK_INSTALL_REEXEC") == "1":
        raise InstallError(
            f"Installer kon niet opnieuw starten met {' '.join(command)}. "
            f"Voer handmatig uit: {' '.join(command)} {REPO_DIR / 'install.py'}"
        )

    env = os.environ.copy()
    env["HENK_INSTALL_REEXEC"] = "1"
    script_path = str(REPO_DIR / "install.py")
    os.execvpe(command[0], command + [script_path], env)


def _bootstrap_python(
    state: InstallState,
    *,
    interactive: bool,
    input_func: Callable[[str], str],
    print_func: Callable[..., None],
) -> list[str]:
    print_func("[ 2/7 ] Bootstrap controleren...")
    env = _detect_python_environment()
    manager = _detect_package_manager()

    if manager:
        state.package_manager = manager.name
    if env.command:
        state.python_command = " ".join(env.command)
        state.python_version = env.version_text

    if env.command and env.version_ok and env.pip_ok:
        state.bootstrap_status = "not_needed"
        state.python_status = "ok"
        print_func(f"  Python {env.version_text} en pip gevonden via: {' '.join(env.command)}. OK\n")
        return env.command

    problem = _python_problem(env)
    instruction = _manual_python_instructions(manager)

    if manager is None or not manager.automatic:
        state.bootstrap_status = "manual_required"
        state.python_status = "error"
        state.notes.append(instruction)
        raise InstallError(f"{problem}. {instruction}")

    state.bootstrap_action = " ".join(manager.install_command or [])
    state.consent_requested = True

    if not interactive:
        state.bootstrap_status = "manual_required"
        state.python_status = "error"
        state.notes.append(f"Voer dit handmatig uit: {state.bootstrap_action}")
        raise InstallError(f"{problem}. Voer dit handmatig uit: {state.bootstrap_action}")

    prompt = f"{problem}. Zal dit commando uitvoeren: {state.bootstrap_action}. Doorgaan? [ja/N] "
    if input_func(prompt).strip().lower() != "ja":
        state.bootstrap_status = "declined"
        state.python_status = "error"
        state.consent_granted = False
        state.notes.append(f"Voer later handmatig uit: {state.bootstrap_action}")
        raise InstallError(f"Bootstrap geannuleerd. Voer dit handmatig uit: {state.bootstrap_action}")

    state.consent_granted = True
    install_result = _run_command(manager.install_command or [])
    if install_result.returncode != 0:
        state.bootstrap_status = "error"
        state.python_status = "error"
        detail = install_result.stderr.strip() or install_result.stdout.strip() or "Onbekende bootstrap-fout."
        raise InstallError(f"Bootstrap voor Python mislukt.\n{detail}")

    env = _detect_python_environment()
    if not env.command or not env.version_ok or not env.pip_ok:
        state.bootstrap_status = "manual_required"
        state.python_status = "error"
        state.notes.append(instruction)
        raise InstallError(f"Python is na bootstrap nog niet bruikbaar. {instruction}")

    state.bootstrap_status = "installed"
    state.python_status = "ok"
    state.python_command = " ".join(env.command)
    state.python_version = env.version_text
    state.bootstrap_interpreter = state.python_command
    if not _current_process_python_ready():
        state.restart_status = "restarting"
        print_func(f"  Python bootstrap voltooid via {manager.name}. OK")
        print_func(f"  Nieuwe interpreter gevonden: {state.python_command}")
        print_func("  Installer start opnieuw met deze Python...\n")
        try:
            _restart_with_python(env.command)
        except OSError as error:
            state.restart_status = "failed"
            raise InstallError(
                f"Python is geïnstalleerd op {state.python_command}, maar herstarten mislukte: {error}. "
                f"Voer handmatig uit: {state.python_command} {REPO_DIR / 'install.py'}"
            ) from error

    state.restart_status = "not_needed"
    print_func(f"  Python bootstrap voltooid via {manager.name}. OK\n")
    return env.command


def _confirm_python_ready(state: InstallState, print_func: Callable[..., None]) -> None:
    print_func("[ 3/7 ] Python en pip controleren...")
    if state.python_status != "ok":
        raise InstallError("Python en pip zijn niet bruikbaar na bootstrap.")
    print_func(f"  Python {state.python_version} klaar via: {state.python_command}. OK\n")


def _install_package(state: InstallState, python_command: list[str], print_func: Callable[..., None]) -> Path:
    title = {
        "install": "Installeren",
        "update": "Bijwerken",
        "repair": "Herstellen",
    }.get(state.mode, "Installeren")
    print_func(f"[ 4/7 ] Henk {title.lower()}...")
    print_func("  (Dit kan even duren de eerste keer)\n")

    user_scripts_dir = _scripts_dir_for_install(python_command, user_install=True)
    global_scripts_dir = _scripts_dir_for_install(python_command, user_install=False)
    result = _run_command(python_command + ["-m", "pip", "install", "--quiet", "--user", "-e", "."], cwd=REPO_DIR)
    if result.returncode != 0:
        print_func("  Proberen zonder --user vlag...")
        result = _run_command(python_command + ["-m", "pip", "install", "--quiet", "-e", "."], cwd=REPO_DIR)
        install_scripts_dir = global_scripts_dir
    else:
        install_scripts_dir = user_scripts_dir

    if result.returncode != 0:
        state.package_status = "error"
        detail = result.stderr.strip() or result.stdout.strip() or "Onbekende pip-fout."
        raise InstallError(f"Installatie mislukt.\n{detail}")

    state.package_status = "ok"
    print_func("  Installatie geslaagd. OK\n")
    return install_scripts_dir


def _check_config(state: InstallState, print_func: Callable[..., None]) -> None:
    print_func("[ 6/7 ] Configuratie controleren...")
    if ENV_FILE.exists():
        state.config_status = "existing"
        print_func("  Configuratiebestand gevonden. OK\n")
        return

    if ENV_EXAMPLE.exists():
        shutil.copy2(ENV_EXAMPLE, ENV_FILE)
        state.config_status = "created"
        state.notes.append(f"Vul API keys in: {ENV_FILE}")
        print_func(f"  Configuratiebestand aangemaakt: {ENV_FILE}")
        print_func("  Vul je API sleutel(s) in voor eerste gebruik.\n")
        return

    state.config_status = "missing_example"
    state.notes.append("Geen .env.example gevonden; maak .env handmatig aan.")
    print_func("  Geen .env.example gevonden. Maak .env handmatig aan.\n")


def _run_henk_init(scripts_dir: Path, python_command: list[str]) -> bool:
    candidates = [scripts_dir / ("henk.exe" if sys.platform == "win32" else "henk")]
    for command_path in candidates:
        if command_path.exists():
            result = _run_command([str(command_path), "init"])
            if result.returncode == 0:
                return True

    result = _run_command(python_command + ["-m", "henk", "init"], cwd=REPO_DIR)
    return result.returncode == 0


def _init_workspace(state: InstallState, scripts_dir: Path, python_command: list[str], print_func: Callable[..., None]) -> None:
    print_func("[ 7/7 ] Henk-werkmap voorbereiden...")
    if HENK_DIR.exists():
        state.workspace_status = "existing"
        print_func("  Bestaande werkmap gevonden. Instellingen blijven bewaard. OK\n")
        return

    if _run_henk_init(scripts_dir, python_command):
        state.workspace_status = "created"
        print_func(f"  Nieuwe werkmap aangemaakt: {HENK_DIR} OK\n")
        return

    state.workspace_status = "deferred"
    state.notes.append("Werkmap wordt aangemaakt bij eerste succesvolle start van Henk.")
    print_func("  Werkmap wordt aangemaakt bij eerste gebruik. OK\n")


def _print_finish(state: InstallState, print_func: Callable[..., None]) -> None:
    print_func("=" * 46)
    print_func("   Installatie voltooid")
    print_func("=" * 46)
    print_func()
    print_func(f"  Platform:      {state.platform}")
    print_func(f"  Modus:         {state.mode}")
    print_func(f"  Bootstrap:     {state.bootstrap_status}")
    print_func(f"  Python:        {state.python_version}")
    if state.python_command:
        print_func(f"  Python cmd:    {state.python_command}")
    if state.package_manager:
        print_func(f"  Package mgr:   {state.package_manager}")
    if state.bootstrap_interpreter:
        print_func(f"  Bootstrap py:  {state.bootstrap_interpreter}")
    print_func(f"  Restart:       {state.restart_status}")
    print_func(f"  Launcher:      {state.launcher_status}")
    print_func()
    print_func("  Start Henk met:")
    print_func("    henk")
    if sys.platform != "win32":
        print_func("    Henk")
    print_func()
    if not state.path_ready:
        print_func("  Als 'henk' niet gevonden wordt, gebruik dan of voeg toe aan PATH:")
        print_func(f"    {state.scripts_dir}")
        print_func()
    for note in state.notes:
        print_func(f"  Let op: {note}")
    if state.notes:
        print_func()


def run_wizard(
    *,
    interactive: bool | None = None,
    input_func: Callable[[str], str] = input,
    print_func: Callable[..., None] = print,
) -> InstallState:
    if interactive is None:
        interactive = _is_interactive()

    _print_header(print_func)
    mode = _choose_mode(interactive, input_func, print_func)
    if mode == "cancel":
        raise SystemExit(0)

    scripts_dir = _user_scripts_dir()
    state = InstallState(
        platform=sys.platform,
        mode=mode,
        scripts_dir=str(scripts_dir),
        path_ready=_path_ready(scripts_dir),
    )
    if not state.path_ready:
        state.notes.append(f"Scripts-dir staat mogelijk niet op PATH: {scripts_dir}")

    _stop_henk(print_func)
    python_command = _bootstrap_python(state, interactive=interactive, input_func=input_func, print_func=print_func)
    _confirm_python_ready(state, print_func)
    scripts_dir = _install_package(state, python_command, print_func)
    _ensure_terminal_command(state, scripts_dir, print_func)
    _check_config(state, print_func)
    _init_workspace(state, scripts_dir, python_command, print_func)
    _print_finish(state, print_func)
    return state


def main() -> None:
    interactive = _is_interactive()
    try:
        run_wizard(interactive=interactive)
    except SystemExit:
        _pause(interactive, input)
        raise
    except InstallError as error:
        print()
        print(f"FOUT: {error}")
        _pause(interactive, input)
        sys.exit(1)

    _pause(interactive, input)


if __name__ == "__main__":
    main()
