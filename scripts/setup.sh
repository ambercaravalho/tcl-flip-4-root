#!/usr/bin/env bash
# One-time setup: create the local .venv and install the runtime deps for the
# vendored edl tool. Safe to re-run.
#
# Usage: scripts/setup.sh [python-interpreter]
#   e.g. scripts/setup.sh            (uses `python3` from PATH)
#        scripts/setup.sh python3.12 (use a specific interpreter)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

PYTHON_BIN="${1:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "error: '$PYTHON_BIN' not found. Install Python 3, or pass an interpreter path." >&2
  exit 1
fi

echo ">> Creating virtualenv in .venv (using $PYTHON_BIN)"
"$PYTHON_BIN" -m venv .venv

echo ">> Upgrading pip"
.venv/bin/python -m pip install --quiet --upgrade pip

echo ">> Installing runtime dependencies (requirements.txt)"
.venv/bin/python -m pip install -r requirements.txt

echo ">> Verifying the vendored edl tool loads"
PYTHONPATH="$DIR/third_party" .venv/bin/python -m edlclient.edl --help >/dev/null

cat <<'EOF'

Setup complete.

Next steps:
  1. Put the phone in EDL mode and connect USB (see README).
  2. scripts/check-device.sh        # confirm the 9008 device is visible
  3. scripts/backup.sh              # make a full backup

On Linux, you may also need the udev rules in linux/ (see README).
EOF
