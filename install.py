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
    consent_requested: bool = False
    consent_granted: bool = False
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


def _path_ready(scripts_dir: Path) -> bool:
    path_entries = [Path(part).expanduser() for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    return scripts_dir.expanduser() in path_entries


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
    print_func("[ 1/6 ] Actieve Henk-processen stoppen...")
    if sys.platform == "win32":
        _run_command(["taskkill", "/F", "/FI", "IMAGENAME eq henk.exe"])
        _run_command(["taskkill", "/F", "/FI", "WINDOWTITLE eq henk*"])
    else:
        _run_command(["pkill", "-TERM", "-f", "python.*henk"])
        _run_command(["pkill", "-TERM", "-f", "[/]henk$"])
    print_func("  Klaar. OK\n")


def _detect_python_environment() -> PythonEnvironment:
    candidates: list[list[str]] = []
    if sys.executable:
        candidates.append([sys.executable])
    if sys.platform == "win32":
        candidates.extend([["py", "-3"], ["python"], ["python3"]])
    else:
        candidates.extend([["python3"], ["python"]])

    seen: set[str] = set()
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
        return PythonEnvironment(
            command=command,
            version_text=version_text,
            version_ok=major > 3 or (major == 3 and minor >= 11),
            pip_ok=pip_result.returncode == 0,
        )

    return PythonEnvironment(command=None)


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


def _bootstrap_python(
    state: InstallState,
    *,
    interactive: bool,
    input_func: Callable[[str], str],
    print_func: Callable[..., None],
) -> list[str]:
    print_func("[ 2/6 ] Bootstrap controleren...")
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
    print_func(f"  Python bootstrap voltooid via {manager.name}. OK\n")
    return env.command


def _confirm_python_ready(state: InstallState, print_func: Callable[..., None]) -> None:
    print_func("[ 3/6 ] Python en pip controleren...")
    if state.python_status != "ok":
        raise InstallError("Python en pip zijn niet bruikbaar na bootstrap.")
    print_func(f"  Python {state.python_version} klaar via: {state.python_command}. OK\n")


def _install_package(state: InstallState, python_command: list[str], print_func: Callable[..., None]) -> None:
    title = {
        "install": "Installeren",
        "update": "Bijwerken",
        "repair": "Herstellen",
    }.get(state.mode, "Installeren")
    print_func(f"[ 4/6 ] Henk {title.lower()}...")
    print_func("  (Dit kan even duren de eerste keer)\n")

    result = _run_command(python_command + ["-m", "pip", "install", "--quiet", "--user", "-e", "."], cwd=REPO_DIR)
    if result.returncode != 0:
        print_func("  Proberen zonder --user vlag...")
        result = _run_command(python_command + ["-m", "pip", "install", "--quiet", "-e", "."], cwd=REPO_DIR)

    if result.returncode != 0:
        state.package_status = "error"
        detail = result.stderr.strip() or result.stdout.strip() or "Onbekende pip-fout."
        raise InstallError(f"Installatie mislukt.\n{detail}")

    state.package_status = "ok"
    print_func("  Installatie geslaagd. OK\n")


def _check_config(state: InstallState, print_func: Callable[..., None]) -> None:
    print_func("[ 5/6 ] Configuratie controleren...")
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
    print_func("[ 6/6 ] Henk-werkmap voorbereiden...")
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
    print_func()
    print_func("  Start Henk met:")
    print_func("    henk")
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
    _install_package(state, python_command, print_func)
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
