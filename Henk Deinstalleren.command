#!/bin/bash
# Finder-dubbelklikbare macOS launcher voor de deinstallatie.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export HENK_SKIP_INTERNAL_PAUSE=1
STATUS=0

if command -v python3 >/dev/null 2>&1; then
    python3 deinstalleer.py || STATUS=$?
elif command -v python >/dev/null 2>&1; then
    python deinstalleer.py || STATUS=$?
else
    echo "Python 3.11 of hoger is vereist. Installeer Python via https://python.org"
    STATUS=1
fi

read -rp "Druk op Enter om dit venster te sluiten..."
exit "$STATUS"
