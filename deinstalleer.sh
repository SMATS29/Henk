#!/bin/bash
# =============================================================================
#   HENK - Deïnstallatie Script
#   Verwijdert de live versie van Henk.
#   De code in deze map blijft veilig bewaard.
# =============================================================================

HENK_DIR="$HOME/henk"
USER_BIN_DIRS=(
    "$HOME/.local/bin"
    "$HOME/Library/Python/3.11/bin"
    "$HOME/Library/Python/3.12/bin"
    "$HOME/Library/Python/3.13/bin"
    "$HOME/Library/Python/3.14/bin"
)

for PYTHON_CMD in python3.14 python3.13 python3.12 python3.11 python3 python; do
    if command -v "$PYTHON_CMD" >/dev/null 2>&1; then
        DETECTED_BIN="$("$PYTHON_CMD" -c "import sysconfig; print(sysconfig.get_path('scripts', 'posix_user'))" 2>/dev/null || true)"
        if [ -n "$DETECTED_BIN" ]; then
            USER_BIN_DIRS+=("$DETECTED_BIN")
        fi
    fi
done

clear
echo "=============================================="
echo "   HENK - Deïnstallatie"
echo "=============================================="
echo ""
echo "  Dit script verwijdert de live versie van Henk:"
echo ""
echo "    - Het 'henk' commando (pip pakket)"
echo "    - Alle herinneringen en instellingen ($HENK_DIR)"
echo ""
echo "  De code in deze map blijft VOLLEDIG BEWAARD."
echo "  Je kunt Henk daarna opnieuw installeren via"
echo "  Henk Installeren.command of installeer.sh."
echo ""
echo "----------------------------------------------"
echo ""

# Bevestiging vragen
read -rp "  Weet je het zeker? Type 'ja' en druk Enter: " BEVESTIGING
echo ""

if [ "$BEVESTIGING" != "ja" ]; then
    echo "  Geannuleerd. Er is niets verwijderd."
    echo ""
    read -rp "Druk op Enter om te sluiten..."
    exit 0
fi

echo ""
echo "  Henk wordt nu verwijderd..."
echo ""

# --------------------------------------------------------------------------
# Stap 1: Actieve processen stoppen
# --------------------------------------------------------------------------
echo "[ 1/3 ] Actieve Henk-processen stoppen..."

# Zoek naar draaiende henk-processen (python + henk, of de henk binary)
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
# Stap 2: Pip pakket verwijderen
# --------------------------------------------------------------------------
echo "[ 2/3 ] Henk pakket verwijderen..."

PACKAGE_REMOVED=0
PACKAGE_FOUND=0

for PYTHON_CMD in python3.14 python3.13 python3.12 python3.11 python3 python; do
    if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
        continue
    fi

    if "$PYTHON_CMD" -m pip show henk >/dev/null 2>&1; then
        PACKAGE_FOUND=1
        if "$PYTHON_CMD" -m pip uninstall henk -y --quiet >/dev/null 2>&1; then
            PACKAGE_REMOVED=1
        fi
    fi
done

if [ "$PACKAGE_FOUND" -eq 0 ]; then
    for PIP_CMD in pip3 pip; do
        if ! command -v "$PIP_CMD" >/dev/null 2>&1; then
            continue
        fi

        if "$PIP_CMD" show henk >/dev/null 2>&1; then
            PACKAGE_FOUND=1
            if "$PIP_CMD" uninstall henk -y --quiet >/dev/null 2>&1; then
                PACKAGE_REMOVED=1
            fi
        fi
    done
fi

if [ "$PACKAGE_REMOVED" -eq 1 ]; then
    echo "  Pakket verwijderd. OK"
elif [ "$PACKAGE_FOUND" -eq 1 ]; then
    echo "  Pakket gevonden, maar verwijderen gaf geen bruikbare output. Controleer eventueel handmatig."
else
    echo "  Henk pakket was al niet geïnstalleerd of pip ontbreekt. OK"
fi

BINARY_REMOVED=0
SEEN_BIN_DIRS=""
for USER_BIN in "${USER_BIN_DIRS[@]}"; do
    [ -n "$USER_BIN" ] || continue
    case ":$SEEN_BIN_DIRS:" in
        *":$USER_BIN:"*)
            continue
            ;;
    esac
    SEEN_BIN_DIRS="${SEEN_BIN_DIRS}:$USER_BIN"

    if [ -f "$USER_BIN/henk" ]; then
        rm -f "$USER_BIN/henk"
        BINARY_REMOVED=1
    fi
done

if [ "$BINARY_REMOVED" -eq 1 ]; then
    echo "  Uitvoerbaar bestand verwijderd. OK"
else
    echo "  Geen los uitvoerbaar bestand gevonden. OK"
fi
echo ""

# --------------------------------------------------------------------------
# Stap 3: Werkmap verwijderen (herinneringen, logs, instellingen)
# --------------------------------------------------------------------------
echo "[ 3/3 ] Werkmap verwijderen ($HENK_DIR)..."

if [ -d "$HENK_DIR" ]; then
    rm -rf "$HENK_DIR"
    if [ ! -d "$HENK_DIR" ]; then
        echo "  Werkmap verwijderd. OK"
    else
        echo "  FOUT: Werkmap kon niet worden verwijderd."
    fi
else
    echo "  Werkmap bestond al niet. OK"
fi
echo ""

# --------------------------------------------------------------------------
# Klaar!
# --------------------------------------------------------------------------
echo "=============================================="
echo "   Deïnstallatie voltooid!"
echo "=============================================="
echo ""
echo "  Henk is volledig verwijderd van dit systeem."
echo ""
echo "  De code in deze map is NIET verwijderd."
echo "  Klik op Henk Installeren.command om Henk"
echo "  opnieuw te installeren — helemaal schoon en nieuw."
echo ""

read -rp "Druk op Enter om dit venster te sluiten..."
