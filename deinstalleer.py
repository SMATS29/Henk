#!/usr/bin/env python3
"""Cross-platform deïnstallatie-wizard voor Henk.

Gebruik:
    python deinstalleer.py
    python3 deinstalleer.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

HENK_DIR = Path.home() / "henk"

PATH_BLOCK_START = "# >>> Henk PATH >>>"
PATH_BLOCK_END = "# <<< Henk PATH <<<"


class UninstallError(RuntimeError):
    """Afbreekfout voor deïnstallatiestappen."""


@dataclass
class UninstallState:
    platform: str
    processes_stopped: bool = False
    package_removed: bool = False
    path_cleaned: bool = False
    workspace_removed: bool = False
    notes: list[str] = field(default_factory=list)


def _run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, cwd=str(cwd) if cwd else None)


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _pause(interactive: bool, input_func: Callable[[str], str]) -> None:
    if interactive and os.environ.get("HENK_SKIP_INTERNAL_PAUSE") != "1":
        input_func("Druk op Enter om dit venster te sluiten...")


def _user_scripts_dir() -> Path:
    if sys.platform == "win32":
        return Path(sysconfig.get_path("scripts", "nt_user"))
    return Path(sysconfig.get_path("scripts", "posix_user"))


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


def _remove_text_block(path: Path, start_marker: str, end_marker: str) -> bool:
    """Verwijder een markerblok uit een bestand. Retourneert True als het bestand gewijzigd is."""
    if not path.exists():
        return False

    content = path.read_text(encoding="utf-8")
    if start_marker not in content or end_marker not in content:
        return False

    before, _, remainder = content.partition(start_marker)
    _, _, after = remainder.partition(end_marker)

    # Verwijder extra lege regels rond het verwijderde blok
    new_content = before.rstrip("\n") + after.lstrip("\n")
    if new_content and not new_content.endswith("\n"):
        new_content += "\n"
    if not new_content.strip():
        new_content = ""

    if new_content == content:
        return False

    path.write_text(new_content, encoding="utf-8")
    return True


def _print_header(print_func: Callable[..., None]) -> None:
    print_func("=" * 46)
    print_func("   HENK - Deïnstallatie Wizard")
    print_func("=" * 46)
    print_func()
    print_func("  Dit verwijdert de live versie van Henk:")
    print_func()
    print_func("    - Het 'henk' commando (pip pakket)")
    print_func(f"    - Alle herinneringen en instellingen ({HENK_DIR})")
    print_func()
    print_func("  De code in deze map blijft VOLLEDIG BEWAARD.")
    print_func("  Je kunt Henk daarna opnieuw installeren via")
    print_func("  Henk Installeren.command, installeer.sh,")
    print_func("  of Henk Installeren.bat.")
    print_func()
    print_func("-" * 46)
    print_func()


def _confirm(interactive: bool, input_func: Callable[[str], str], print_func: Callable[..., None]) -> bool:
    if not interactive:
        return True

    answer = input_func("  Weet je het zeker? Type 'ja' en druk Enter: ").strip().lower()
    print_func()
    return answer == "ja"


def _stop_processes(state: UninstallState, print_func: Callable[..., None]) -> None:
    print_func("[ 1/4 ] Actieve Henk-processen stoppen...")

    if sys.platform == "win32":
        _run_command(["taskkill", "/F", "/FI", "IMAGENAME eq henk.exe"])
        _run_command(["taskkill", "/F", "/FI", "WINDOWTITLE eq henk*"])
    else:
        _run_command(["pkill", "-TERM", "-f", "python.*henk"])
        _run_command(["pkill", "-TERM", "-f", "[/]henk$"])
        time.sleep(2)
        _run_command(["pkill", "-KILL", "-f", "python.*henk"])
        _run_command(["pkill", "-KILL", "-f", "[/]henk$"])

    state.processes_stopped = True
    print_func("  Klaar. OK\n")


def _remove_package(state: UninstallState, print_func: Callable[..., None]) -> None:
    print_func("[ 2/4 ] Henk pakket verwijderen...")

    candidates: list[list[str]] = []
    if sys.platform == "win32":
        candidates.extend([["py", "-3"], ["python"], ["python3"]])
    else:
        for minor in range(14, 10, -1):
            candidates.append([f"python3.{minor}"])
        candidates.extend([["python3"], ["python"]])

    removed = False
    for command in candidates:
        show_result = _run_command(command + ["-m", "pip", "show", "henk"])
        if show_result.returncode != 0:
            continue

        uninstall_result = _run_command(command + ["-m", "pip", "uninstall", "henk", "-y", "--quiet"])
        if uninstall_result.returncode == 0:
            removed = True
            break

    state.package_removed = removed
    if removed:
        print_func("  Pakket verwijderd. OK\n")
    else:
        print_func("  Henk pakket was al niet geïnstalleerd of pip ontbreekt. OK\n")


def _clean_path(state: UninstallState, print_func: Callable[..., None]) -> None:
    print_func("[ 3/4 ] PATH opruimen...")

    cleaned = False
    if sys.platform == "win32":
        cleaned = _clean_windows_path()
    else:
        for target in _posix_profile_targets():
            if _remove_text_block(target, PATH_BLOCK_START, PATH_BLOCK_END):
                cleaned = True

    state.path_cleaned = cleaned
    if cleaned:
        print_func("  PATH-configuratie opgeruimd. OK\n")
    else:
        print_func("  Geen PATH-configuratie gevonden om op te ruimen. OK\n")


def _clean_windows_path() -> bool:
    if sys.platform != "win32":
        return False

    try:
        import winreg
    except ImportError:
        return False

    scripts_dir = str(_user_scripts_dir().expanduser())
    normalized_target = os.path.normcase(scripts_dir)

    try:
        access = winreg.KEY_READ | winreg.KEY_SET_VALUE
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, access) as key:
            try:
                current_value, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                return False

            entries = [entry for entry in current_value.split(os.pathsep) if entry]
            new_entries = [entry for entry in entries if os.path.normcase(entry) != normalized_target]

            if len(new_entries) == len(entries):
                return False

            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, os.pathsep.join(new_entries))
    except OSError:
        return False

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


def _remove_workspace(state: UninstallState, print_func: Callable[..., None]) -> None:
    print_func(f"[ 4/4 ] Werkmap verwijderen ({HENK_DIR})...")

    if not HENK_DIR.exists():
        state.workspace_removed = True
        print_func("  Werkmap bestond al niet. OK\n")
        return

    try:
        shutil.rmtree(HENK_DIR)
        state.workspace_removed = True
        print_func("  Werkmap verwijderd. OK\n")
    except PermissionError as error:
        state.workspace_removed = False
        state.notes.append(f"Werkmap kon niet worden verwijderd: {error}")
        print_func(f"  FOUT: Werkmap kon niet worden verwijderd: {error}\n")


def _print_finish(state: UninstallState, print_func: Callable[..., None]) -> None:
    print_func("=" * 46)
    print_func("   Deïnstallatie voltooid!")
    print_func("=" * 46)
    print_func()
    print_func("  Henk is volledig verwijderd van dit systeem.")
    print_func()
    print_func("  De code in deze map is NIET verwijderd.")
    print_func("  Klik op Henk Installeren.command,")
    print_func("  Henk Installeren.bat, of gebruik installeer.sh")
    print_func("  om Henk opnieuw te installeren.")
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
) -> UninstallState:
    if interactive is None:
        interactive = _is_interactive()

    state = UninstallState(platform=sys.platform)

    _print_header(print_func)

    if not _confirm(interactive, input_func, print_func):
        print_func("  Geannuleerd. Er is niets verwijderd.")
        print_func()
        return state

    _stop_processes(state, print_func)
    _remove_package(state, print_func)
    _clean_path(state, print_func)
    _remove_workspace(state, print_func)
    _print_finish(state, print_func)

    return state


def main() -> None:
    interactive = _is_interactive()
    try:
        run_wizard(interactive=interactive)
    except SystemExit:
        _pause(interactive, input)
        raise
    except UninstallError as error:
        print()
        print(f"FOUT: {error}")
        _pause(interactive, input)
        sys.exit(1)

    _pause(interactive, input)


if __name__ == "__main__":
    main()
