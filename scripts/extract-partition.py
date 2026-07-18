#!/usr/bin/env python3
"""Carve a named partition out of a full raw eMMC image, offline.

This never touches the device. It parses the GPT embedded in the image and
copies one partition to a file, so you can inspect/patch boot, vbmeta, etc.
without re-reading the phone.

Usage:
    scripts/extract-partition.py <image> <partition-name> <output>
    scripts/extract-partition.py <image> --list

Example:
    scripts/extract-partition.py backups/flip4-full-emmc.img vbmeta_b build/vbmeta_b.img
"""
import struct
import sys

SECTOR = 512


def read_gpt(fh):
    """Return list of (name, first_lba, last_lba) from the primary GPT."""
    fh.seek(1 * SECTOR)
    header = fh.read(SECTOR)
    if header[0:8] != b"EFI PART":
        raise SystemExit("error: no GPT signature (EFI PART) at LBA 1")
    part_entry_lba = struct.unpack_from("<Q", header, 72)[0]
    num_entries = struct.unpack_from("<I", header, 80)[0]
    entry_size = struct.unpack_from("<I", header, 84)[0]

    fh.seek(part_entry_lba * SECTOR)
    table = fh.read(num_entries * entry_size)

    parts = []
    for i in range(num_entries):
        entry = table[i * entry_size:(i + 1) * entry_size]
        type_guid = entry[0:16]
        if type_guid == b"\x00" * 16:
            continue
        first_lba, last_lba = struct.unpack_from("<QQ", entry, 32)
        name = entry[56:128].decode("utf-16-le").rstrip("\x00")
        parts.append((name, first_lba, last_lba))
    return parts


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    image = argv[1]
    with open(image, "rb") as fh:
        parts = read_gpt(fh)

        if argv[2] == "--list":
            print(f"{'partition':24} {'first_lba':>12} {'sectors':>12} {'size':>14}")
            for name, first, last in parts:
                sectors = last - first + 1
                print(f"{name:24} {first:>12} {sectors:>12} {sectors * SECTOR:>14}")
            return 0

        if len(argv) < 4:
            raise SystemExit(__doc__)
        target, output = argv[2], argv[3]
        match = next((p for p in parts if p[0] == target), None)
        if match is None:
            raise SystemExit(f"error: partition '{target}' not found (try --list)")

        _, first, last = match
        offset = first * SECTOR
        length = (last - first + 1) * SECTOR
        fh.seek(offset)
        with open(output, "wb") as out:
            remaining = length
            while remaining:
                chunk = fh.read(min(1 << 20, remaining))
                if not chunk:
                    break
                out.write(chunk)
                remaining -= len(chunk)
        print(f"wrote {output}: {length} bytes from {target} "
              f"(offset {offset:#x}, {length // SECTOR} sectors)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
