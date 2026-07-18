#!/usr/bin/env python3
"""Surgically patch one hashtree descriptor's root_digest in a signed vbmeta
image, then re-sign, leaving every other descriptor byte-identical.

This is used to update ONLY the `odm` descriptor after making its precompiled
SELinux policy permissive, without disturbing dtbo/init_boot/vendor_boot/vendor/
system_dlkm/vendor_dlkm/chain descriptors (which the full-rebuild path cannot
reproduce for hash-only partitions like dtbo).

AVB signature == RSA-PKCS1v1.5(SHA256(header || aux)), which is exactly what
`openssl dgst -sha256 -sign` produces, so we shell out to openssl for signing.

Usage:
  patch_vbmeta.py <stock_vbmeta> <partition> <new_root_digest_hex> <key.pem> <out> [--zero-fec]
"""
import hashlib
import struct
import subprocess
import sys

DESC_HASHTREE = 1


def find_and_patch(aux, desc_off, desc_size, target, new_digest, zero_fec):
    """Return patched aux bytes; raise if target not found."""
    aux = bytearray(aux)
    pos = desc_off
    end = desc_off + desc_size
    while pos < end:
        tag, nbf = struct.unpack_from(">QQ", aux, pos)
        body = pos + 16
        total = 16 + nbf
        if tag == DESC_HASHTREE:
            # Offsets are relative to the descriptor body (after the 16-byte
            # AvbDescriptor base): hash_algorithm(32s)@56, then
            # partition_name_len@88, salt_len@92, root_digest_len@96, flags@100,
            # reserved(60)@104, and the name/salt/digest blob starts at @164.
            name_len = struct.unpack_from(">L", aux, body + 88)[0]
            salt_len = struct.unpack_from(">L", aux, body + 92)[0]
            digest_len = struct.unpack_from(">L", aux, body + 96)[0]
            name_off = body + 164
            name = aux[name_off:name_off + name_len].decode()
            if name == target:
                if len(new_digest) != digest_len:
                    raise SystemExit(
                        f"digest len {len(new_digest)} != expected {digest_len}")
                if zero_fec:
                    struct.pack_into(">L", aux, body + 36, 0)   # fec_num_roots
                    struct.pack_into(">Q", aux, body + 40, 0)   # fec_offset
                    struct.pack_into(">Q", aux, body + 48, 0)   # fec_size
                digest_off = name_off + name_len + salt_len
                aux[digest_off:digest_off + digest_len] = new_digest
                return bytes(aux)
        pos += total
    raise SystemExit(f"hashtree descriptor '{target}' not found")


def main(argv):
    if len(argv) < 6:
        raise SystemExit(__doc__)
    stock, part, digest_hex, key, out = argv[1:6]
    zero_fec = "--zero-fec" in argv[6:]
    new_digest = bytes.fromhex(digest_hex)

    data = open(stock, "rb").read()
    if data[0:4] != b"AVB0":
        raise SystemExit("not a vbmeta image (missing AVB0 magic)")

    auth_size = struct.unpack_from(">Q", data, 12)[0]
    aux_size = struct.unpack_from(">Q", data, 20)[0]
    hash_off = struct.unpack_from(">Q", data, 32)[0]
    hash_size = struct.unpack_from(">Q", data, 40)[0]
    sig_off = struct.unpack_from(">Q", data, 48)[0]
    sig_size = struct.unpack_from(">Q", data, 56)[0]
    desc_off = struct.unpack_from(">Q", data, 96)[0]
    desc_size = struct.unpack_from(">Q", data, 104)[0]

    header = data[0:256]
    aux_start = 256 + auth_size
    aux = data[aux_start:aux_start + aux_size]
    total_size = len(data)

    new_aux = find_and_patch(aux, desc_off, desc_size, part, new_digest, zero_fec)

    # AVB signs SHA256(header || aux) with PKCS#1 v1.5 -> openssl dgst -sha256 -sign
    signed_input = header + new_aux
    proc = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", key],
        input=signed_input, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit("openssl sign failed: " + proc.stderr.decode())
    signature = proc.stdout
    if len(signature) != sig_size:
        raise SystemExit(f"sig len {len(signature)} != header sig_size {sig_size}")

    digest = hashlib.sha256(signed_input).digest()
    if len(digest) != hash_size:
        raise SystemExit(f"digest len {len(digest)} != header hash_size {hash_size}")

    auth = bytearray(auth_size)
    auth[hash_off:hash_off + hash_size] = digest
    auth[sig_off:sig_off + sig_size] = signature

    blob = header + bytes(auth) + new_aux
    if len(blob) > total_size:
        raise SystemExit("patched blob larger than original")
    blob = blob + b"\x00" * (total_size - len(blob))

    open(out, "wb").write(blob)
    print(f"wrote {out}: {len(blob)} bytes, {part} root_digest -> {digest_hex}"
          f"{' (fec zeroed)' if zero_fec else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
