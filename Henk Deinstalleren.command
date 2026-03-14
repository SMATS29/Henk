#!/bin/bash
# Finder-dubbelklikbare macOS launcher voor de deinstallatie.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

bash deinstalleer.sh
