#!/usr/bin/env bash
# Make a full raw eMMC backup of the TCL Flip 4 and verify it.
#
# This is READ-ONLY on the device. It produces one restorable raw image.
# Requires the phone to be in EDL mode (run scripts/check-device.sh first).
#
# Usage: scripts/backup.sh [output-image]
#   default output: backups/flip4-full-emmc.img
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

OUT="${1:-backups/flip4-full-emmc.img}"
LOADER="loader/flip-4-edl.bin"

mkdir -p "$(dirname "$OUT")" logs

echo ">> Dumping full eMMC to $OUT (this takes ~15 min at ~35 MB/s)"
# --skipresponse is REQUIRED for this loader (see docs/PATCHES.md).
scripts/edl rf "$OUT" --loader="$LOADER" --memory=emmc --skipresponse | tee "logs/backup.log"

echo
echo ">> Verifying image ..."
.venv/bin/python - "$OUT" <<'PY'
import os, sys
path = sys.argv[1]
size = os.path.getsize(path)
ok = True
with open(path, "rb") as fh:
    fh.seek(512)
    primary = fh.read(8)
    fh.seek(size - 512)
    backup = fh.read(8)

print(f"  size            : {size} bytes ({size/1024/1024/1024:.2f} GiB)")
print(f"  512-byte aligned: {'yes' if size % 512 == 0 else 'NO'}")
print(f"  primary GPT     : {'valid (EFI PART)' if primary == b'EFI PART' else 'MISSING'}")
print(f"  backup  GPT     : {'valid (EFI PART)' if backup  == b'EFI PART' else 'MISSING'}")

if size % 512 != 0 or primary != b"EFI PART" or backup != b"EFI PART":
    print("  RESULT          : FAILED - image looks incomplete/corrupt")
    sys.exit(1)
print("  RESULT          : OK - primary + backup GPT present, image complete")
PY

echo
echo "Done. Keep this image somewhere safe (it contains personal data)."
echo "To leave EDL mode, pull the battery for ~10s and power on."
