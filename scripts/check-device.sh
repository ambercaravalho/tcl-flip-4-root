#!/usr/bin/env bash
# Check whether the phone is visible in EDL mode (Qualcomm 9008).
#
# Note: on macOS `system_profiler SPUSBDataType` often does NOT list the 9008
# device, so we ask pyusb/libusb directly, which is reliable.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$DIR/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "error: $PY not found. Run scripts/setup.sh first." >&2
  exit 1
fi

exec "$PY" - <<'PY'
import sys
try:
    import usb.core
except Exception as e:
    print("error: pyusb not available:", e)
    sys.exit(2)

dev = usb.core.find(idVendor=0x05c6, idProduct=0x9008)
if dev is not None:
    print("OK: Qualcomm EDL device detected (05c6:9008). Ready for edl commands.")
    sys.exit(0)

print("NOT FOUND: no 05c6:9008 device.")
print("- Make sure the phone is in EDL mode (see README: Entering EDL mode).")
print("- Use a data-capable USB cable and a direct port (not a hub).")
sys.exit(1)
PY
