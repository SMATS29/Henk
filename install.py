#!/usr/bin/env python3
"""Cross-platform installer voor Henk. Werkt op Linux, macOS en Windows.

Gebruik:
    python install.py       (of python3 install.py)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

REPO_DIR = Path(__file__).parent.resolve()
HENK_DIR = Path.home() / "henk"
ENV_FILE = REPO_DIR / ".env"


def _print_header() -> None:
    print("=" * 46)
    print("   HENK - Installatie & Update")
    print("=" * 46)
    print()


def _user_scripts_dir() -> Path:
    """Geeft het platform-juiste pip user scripts-pad terug."""
    if sys.platform == "win32":
        return Path(sysconfig.get_path("scripts", "nt_user"))
    return Path(sysconfig.get_path("scripts", "posix_user"))


def _stop_henk() -> None:
    print("[ 1/5 ] Actieve Henk-processen stoppen...")
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/FI", "IMAGENAME eq henk.exe"],
                       capture_output=True)
        subprocess.run(["taskkill", "/F", "/FI", "WINDOWTITLE eq henk*"],
                       capture_output=True)
    else:
        subprocess.run(["pkill", "-TERM", "-f", "python.*henk"],
                       capture_output=True)
        subprocess.run(["pkill", "-TERM", "-f", "[/]henk$"],
                       capture_output=True)
    print("  Klaar. OK\n")


def _check_python() -> None:
    print("[ 2/5 ] Python controleren...")
    major, minor = sys.version_info.major, sys.version_info.minor
    if major < 3 or (major == 3 and minor < 11):
        print(f"  FOUT: Python {major}.{minor} gevonden, maar 3.11+ vereist.")
        print("  Download de nieuwste versie via: https://python.org")
        _pause_and_exit(1)
    print(f"  Python {major}.{minor} gevonden. OK\n")


def _install_package() -> None:
    print("[ 3/5 ] Henk installeren / bijwerken...")
    print("  (Dit kan even duren de eerste keer)\n")
    os.chdir(REPO_DIR)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--user", "-e", "."],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Probeer zonder --user (bijv. in een venv)
        print("  Proberen zonder --user vlag...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "-e", "."],
            capture_output=True, text=True,
        )
    if result.returncode != 0:
        print("  FOUT: Installatie mislukt.")
        print(result.stderr)
        _pause_and_exit(1)
    print("  Installatie geslaagd. OK\n")


def _check_config() -> None:
    print("[ 4/5 ] Configuratie controleren...")
    if not ENV_FILE.exists():
        example = REPO_DIR / ".env.example"
        if example.exists():
            shutil.copy2(example, ENV_FILE)
            print()
            print("  *** ACTIE VEREIST ***")
            print()
            print(f"  Het configuratiebestand is aangemaakt:")
            print(f"  {ENV_FILE}")
            print()
            print("  Vul je API sleutel(s) in dit bestand in.")
            print("  Open het met een teksteditor en vervang de")
            print("  placeholder-tekst door je echte sleutels.")
            print()
            print("  Minimaal vereist (kies één):")
            print("    ANTHROPIC_API_KEY  → claude.ai/settings/keys")
            print("    OPENAI_API_KEY     → platform.openai.com/api-keys")
            print()
        else:
            print("  Geen .env bestand gevonden. Maak handmatig aan.")
    else:
        print("  Configuratiebestand gevonden. OK")
    print()


def _init_workspace(scripts_dir: Path) -> None:
    print("[ 5/5 ] Henk-werkmap voorbereiden...")
    if HENK_DIR.exists():
        print("  Bestaande installatie bijgewerkt.")
        print("  Instellingen en herinneringen blijven bewaard. OK")
    else:
        print("  Henk wordt voor het eerst geïnstalleerd...")
        henk_cmd = scripts_dir / ("henk.exe" if sys.platform == "win32" else "henk")
        ran_ok = False
        if henk_cmd.exists():
            r = subprocess.run([str(henk_cmd), "init"], capture_output=True)
            ran_ok = r.returncode == 0
        if not ran_ok:
            r = subprocess.run(
                [sys.executable, "-m", "henk", "init"], capture_output=True
            )
            ran_ok = r.returncode == 0
        if ran_ok:
            print(f"  Nieuwe werkmap aangemaakt: {HENK_DIR} OK")
        else:
            print("  Werkmap wordt aangemaakt bij eerste gebruik. OK")
    print()


def _print_finish(scripts_dir: Path) -> None:
    print("=" * 46)
    print("   Installatie voltooid!")
    print("=" * 46)
    print()
    print("  Henk is klaar voor gebruik.")
    print()
    print("  Start Henk door een terminal te openen en")
    print("  het volgende te typen:  henk")
    print()
    if sys.platform == "win32":
        print("  Als 'henk' niet herkend wordt, voeg dit toe")
        print("  aan je PATH-omgevingsvariabele:")
        print(f"  {scripts_dir}")
    else:
        print("  Als 'henk' niet gevonden wordt, sluit dan")
        print("  de terminal en open een nieuwe.")
    print()


def _pause_and_exit(code: int = 0) -> None:
    input("Druk op Enter om dit venster te sluiten...")
    sys.exit(code)


def main() -> None:
    _print_header()
    _stop_henk()
    _check_python()
    _install_package()
    _check_config()
    scripts_dir = _user_scripts_dir()
    _init_workspace(scripts_dir)
    _print_finish(scripts_dir)
    _pause_and_exit(0)


if __name__ == "__main__":
    main()
