#!/bin/bash
# =============================================================================
#   HENK - Deïnstallatie Script
#   Verwijdert de live versie van Henk.
#   De code in deze map blijft veilig bewaard.
# =============================================================================

HENK_DIR="$HOME/henk"

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
echo "  installeer.sh — helemaal schoon en nieuw."
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
# Stap 1: Pip pakket verwijderen
# --------------------------------------------------------------------------
echo "[ 1/2 ] Henk pakket verwijderen..."

# Kies het juiste pip commando
if command -v pip3 &>/dev/null; then
    PIP="pip3"
elif command -v pip &>/dev/null; then
    PIP="pip"
else
    PIP="python3 -m pip"
fi

if $PIP show henk &>/dev/null 2>&1; then
    if $PIP uninstall henk -y --quiet 2>&1; then
        echo "  Pakket verwijderd. OK"
    else
        echo "  Pakket verwijderen mislukt (mogelijk al niet geïnstalleerd)."
    fi
else
    echo "  Henk pakket was al niet geïnstalleerd. OK"
fi

# Verwijder ook het binaire bestand als het nog bestaat
if [ -f "$HOME/.local/bin/henk" ]; then
    rm -f "$HOME/.local/bin/henk"
    echo "  Uitvoerbaar bestand verwijderd. OK"
fi
echo ""

# --------------------------------------------------------------------------
# Stap 2: Werkmap verwijderen (herinneringen, logs, instellingen)
# --------------------------------------------------------------------------
echo "[ 2/2 ] Werkmap verwijderen ($HENK_DIR)..."

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
echo "  Klik op installeer.sh om Henk opnieuw"
echo "  te installeren — helemaal schoon en nieuw."
echo ""

read -rp "Druk op Enter om dit venster te sluiten..."
