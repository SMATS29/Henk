#!/bin/bash
# Dunne wrapper naar de cross-platform install wizard.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
    python3 install.py
elif command -v python >/dev/null 2>&1; then
    python install.py
else
    echo "Python 3.11 of hoger is vereist. Installeer Python via https://python.org"
    read -rp "Druk op Enter om te sluiten..."
    exit 1
fi
