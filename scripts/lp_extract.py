#!/usr/bin/env python3
"""Minimal Android liblp (super/dynamic partitions) reader.

Parses the LP metadata in a super image and can list logical partitions or
extract one to a file (by concatenating its linear extents). Pure stdlib.

Usage:
    scripts/lp_extract.py <super.img> --list
    scripts/lp_extract.py <super.img> <partition> <output>

Reference: system/core/fs_mgr/liblp (LpMetadata* structs).
"""
import struct
import sys

SECTOR = 512
GEOMETRY_OFFSET = 4096          # LP_PARTITION_RESERVED_BYTES
GEOMETRY_SIZE = 4096            # LP_METADATA_GEOMETRY_SIZE
GEOMETRY_MAGIC = 0x616C4467     # "gDla" little-endian
HEADER_MAGIC = 0x414C5030       # "0PLA" little-endian ("LP\x30" ordering)


def _read_geometry(fh):
    fh.seek(GEOMETRY_OFFSET)
    data = fh.read(GEOMETRY_SIZE)
    magic, struct_size = struct.unpack_from("<II", data, 0)
    if magic != GEOMETRY_MAGIC:
        raise SystemExit(f"error: bad geometry magic {magic:#x}")
    # after magic(4) struct_size(4) checksum(32):
    metadata_max_size, metadata_slot_count, logical_block_size = \
        struct.unpack_from("<III", data, 40)
    return metadata_max_size, metadata_slot_count, logical_block_size


def _read_metadata(fh, metadata_max_size, slot=0):
    # Primary metadata slots start right after primary+backup geometry,
    # each occupying metadata_max_size bytes.
    slot0 = GEOMETRY_OFFSET + GEOMETRY_SIZE * 2 + metadata_max_size * slot
    fh.seek(slot0)
    header = fh.read(256)
    magic = struct.unpack_from("<I", header, 0)[0]
    if magic != HEADER_MAGIC:
        raise SystemExit(f"error: bad metadata header magic {magic:#x}")
    header_size = struct.unpack_from("<I", header, 8)[0]
    # Layout: magic(4) major(2) minor(2) header_size(4) header_csum(32)@12
    #         tables_size(4)@44 tables_csum(32)@48 descriptors@80
    tables_size = struct.unpack_from("<I", header, 44)[0]

    # Table descriptors at 80.. : each is (offset u32, num_entries u32, entry_size u32)
    def desc(idx):
        base = 80 + idx * 12
        off, num, esz = struct.unpack_from("<III", header, base)
        return off, num, esz

    part_off, part_num, part_esz = desc(0)
    ext_off, ext_num, ext_esz = desc(1)

    fh.seek(slot0 + header_size)
    tables = fh.read(tables_size)

    partitions = []
    for i in range(part_num):
        e = tables[part_off + i * part_esz: part_off + (i + 1) * part_esz]
        name = e[0:36].split(b"\x00")[0].decode()
        attributes, first_extent_index, num_extents, group_index = \
            struct.unpack_from("<IIII", e, 36)
        partitions.append((name, first_extent_index, num_extents))

    extents = []
    for i in range(ext_num):
        e = tables[ext_off + i * ext_esz: ext_off + (i + 1) * ext_esz]
        # LpMetadataExtent is packed (24 bytes on disk):
        #   num_sectors u64@0, target_type u32@8, target_data u64@12, target_source u32@20
        num_sectors = struct.unpack_from("<Q", e, 0)[0]
        target_type = struct.unpack_from("<I", e, 8)[0]
        target_data = struct.unpack_from("<Q", e, 12)[0]
        target_source = struct.unpack_from("<I", e, 20)[0]
        extents.append((num_sectors, target_type, target_data, target_source))
    return partitions, extents


def main(argv):
    slot = 0
    argv = [a for a in argv if not (a.startswith("--slot=") and (slot := int(a.split("=", 1)[1])) is not None)]
    if len(argv) < 3:
        raise SystemExit(__doc__)
    image = argv[1]
    with open(image, "rb") as fh:
        mms, slots, lbs = _read_geometry(fh)
        partitions, extents = _read_metadata(fh, mms, slot)

        if argv[2] == "--list":
            print(f"{'partition':22} {'extents':>8} {'total_sectors':>14} {'bytes':>16}")
            for name, fei, ne in partitions:
                total = sum(extents[fei + k][0] for k in range(ne))
                print(f"{name:22} {ne:>8} {total:>14} {total * SECTOR:>16}")
            return 0

        if len(argv) < 4:
            raise SystemExit(__doc__)
        target, output = argv[2], argv[3]
        match = next((p for p in partitions if p[0] == target), None)
        if match is None:
            raise SystemExit(f"error: logical partition '{target}' not found (try --list)")
        _, fei, ne = match
        with open(output, "wb") as out:
            for k in range(ne):
                num_sectors, ttype, tdata, tsource = extents[fei + k]
                if ttype != 0:  # 0 = LINEAR
                    raise SystemExit(f"error: non-linear extent (type {ttype}) unsupported")
                fh.seek(tdata * SECTOR)
                remaining = num_sectors * SECTOR
                print(f"  extent: start_sector={tdata} sectors={num_sectors} "
                      f"({remaining} bytes)")
                while remaining:
                    chunk = fh.read(min(1 << 20, remaining))
                    if not chunk:
                        raise SystemExit("error: short read from super")
                    out.write(chunk)
                    remaining -= len(chunk)
        print(f"wrote {output} for {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
