#!/bin/bash
# =============================================================================
#   HENK - Installatie / Update Script
#   Dubbelklik dit bestand om Henk te installeren of bij te werken.
# =============================================================================

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HENK_DIR="$HOME/henk"
ENV_FILE="$REPO_DIR/.env"

# Zorgt dat het venster open blijft bij een fout
trap 'echo ""; echo "Er is een fout opgetreden. Druk op Enter om te sluiten."; read' ERR

clear
echo "=============================================="
echo "   HENK - Installatie & Update"
echo "=============================================="
echo ""

# --------------------------------------------------------------------------
# Stap 1: Actieve processen stoppen
# --------------------------------------------------------------------------
echo "[ 1/5 ] Actieve Henk-processen stoppen..."

if pgrep -f "python.*henk" &>/dev/null || pgrep -f "[/]henk$" &>/dev/null; then
    echo "  Henk is nog actief. Processen worden gestopt..."

    # Nette afsluiting (geeft het proces kans om op te schonen)
    pkill -TERM -f "python.*henk" 2>/dev/null || true
    pkill -TERM -f "[/]henk$"     2>/dev/null || true
    sleep 2

    # Als processen nog steeds draaien: forceer afsluiting
    if pgrep -f "python.*henk" &>/dev/null || pgrep -f "[/]henk$" &>/dev/null; then
        pkill -KILL -f "python.*henk" 2>/dev/null || true
        pkill -KILL -f "[/]henk$"     2>/dev/null || true
        sleep 1
    fi

    if pgrep -f "python.*henk" &>/dev/null || pgrep -f "[/]henk$" &>/dev/null; then
        echo "  WAARSCHUWING: Sommige processen konden niet gestopt worden."
        echo "  Sluit open Henk-vensters handmatig en probeer opnieuw."
    else
        echo "  Alle processen gestopt. OK"
    fi
else
    echo "  Geen actieve Henk-processen gevonden. OK"
fi
echo ""

# --------------------------------------------------------------------------
# Stap 2: Python controleren
# --------------------------------------------------------------------------
echo "[ 2/5 ] Python controleren..."

if ! command -v python3 &>/dev/null; then
    echo ""
    echo "  FOUT: Python 3 is niet gevonden op dit systeem."
    echo "  Installeer Python 3.11 of hoger via: https://python.org"
    echo ""
    read -rp "Druk op Enter om te sluiten..."
    exit 1
fi

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    echo ""
    echo "  FOUT: Python $PYTHON_VER gevonden, maar versie 3.11 of hoger is vereist."
    echo "  Download de nieuwste versie via: https://python.org"
    echo ""
    read -rp "Druk op Enter om te sluiten..."
    exit 1
fi

echo "  Python $PYTHON_VER gevonden. OK"
echo ""

# --------------------------------------------------------------------------
# Stap 3: Henk installeren of bijwerken
# --------------------------------------------------------------------------
echo "[ 3/5 ] Henk installeren / bijwerken..."
echo "  (Dit kan even duren de eerste keer)"
echo ""

cd "$REPO_DIR"

# Kies het juiste pip commando
if command -v pip3 &>/dev/null; then
    PIP="pip3"
elif command -v pip &>/dev/null; then
    PIP="pip"
else
    PIP="python3 -m pip"
fi

if $PIP install --quiet --user -e . 2>&1; then
    echo "  Installatie geslaagd. OK"
else
    echo ""
    echo "  Proberen met verhoogde rechten..."
    if $PIP install --quiet -e . 2>&1; then
        echo "  Installatie geslaagd. OK"
    else
        echo ""
        echo "  FOUT: Installatie mislukt. Zie foutmelding hierboven."
        read -rp "Druk op Enter om te sluiten..."
        exit 1
    fi
fi
echo ""

# Bepaal het juiste gebruikerspad voor pip-installaties (platform-afhankelijk)
USER_BIN=$(python3 -c "import sysconfig; print(sysconfig.get_path('scripts', 'posix_user'))" 2>/dev/null || echo "$HOME/.local/bin")
export PATH="$USER_BIN:$PATH"

# --------------------------------------------------------------------------
# Stap 4: API sleutels controleren
# --------------------------------------------------------------------------
echo "[ 4/5 ] Configuratie controleren..."

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$REPO_DIR/.env.example" ]; then
        cp "$REPO_DIR/.env.example" "$ENV_FILE"
        echo ""
        echo "  *** ACTIE VEREIST ***"
        echo ""
        echo "  Het configuratiebestand is aangemaakt:"
        echo "  $ENV_FILE"
        echo ""
        echo "  Vul je API sleutel(s) in dit bestand in."
        echo "  Open het met een teksteditor en vervang de"
        echo "  placeholder-tekst door je echte sleutels."
        echo ""
        echo "  Minimaal vereist (kies één):"
        echo "    ANTHROPIC_API_KEY  → claude.ai/settings/keys"
        echo "    OPENAI_API_KEY     → platform.openai.com/api-keys"
        echo ""
    else
        echo "  Geen .env bestand gevonden. Maak handmatig aan."
    fi
else
    echo "  Configuratiebestand gevonden. OK"
fi
echo ""

# --------------------------------------------------------------------------
# Stap 5: Henk-map initialiseren
# --------------------------------------------------------------------------
echo "[ 5/5 ] Henk-werkmap voorbereiden..."

if [ -d "$HENK_DIR" ]; then
    echo "  Bestaande installatie bijgewerkt."
    echo "  Instellingen en herinneringen blijven bewaard. OK"
else
    echo "  Henk wordt voor het eerst geïnstalleerd..."
    # Probeer 'henk init' te draaien
    if command -v henk &>/dev/null; then
        henk init 2>/dev/null && echo "  Nieuwe werkmap aangemaakt: $HENK_DIR OK" \
            || echo "  Werkmap wordt aangemaakt bij eerste gebruik. OK"
    else
        # Henk is in USER_BIN maar nog niet in PATH van dit sessie
        "$USER_BIN/henk" init 2>/dev/null \
            && echo "  Nieuwe werkmap aangemaakt: $HENK_DIR OK" \
            || echo "  Werkmap wordt aangemaakt bij eerste gebruik. OK"
    fi
fi
echo ""

# --------------------------------------------------------------------------
# Klaar!
# --------------------------------------------------------------------------
echo "=============================================="
echo "   Installatie voltooid!"
echo "=============================================="
echo ""
echo "  Henk is klaar voor gebruik."
echo ""
echo "  Start Henk door een terminal te openen en"
echo "  het volgende te typen:  henk"
echo ""
echo "  Als 'henk' niet gevonden wordt, sluit dan"
echo "  de terminal en open een nieuwe."
echo ""

read -rp "Druk op Enter om dit venster te sluiten..."
