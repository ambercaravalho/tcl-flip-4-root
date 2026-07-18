# TCL Flip 4 - EDL Firehose capabilities

This is the full capability reference for the TCL Flip 4's firehose loader
(`loader/flip-4-edl.bin`), mapped to concrete `edl` commands.

For an overview and setup, see the [README](../README.md). For why the tool is
patched and why `--skipresponse` is required, see [PATCHES.md](PATCHES.md).

## How to read this doc

- Every command goes through the wrapper: **`scripts/edl <command> ...`**.
- Common flags used everywhere on this device:
  `--loader=loader/flip-4-edl.bin --memory=emmc --skipresponse`
- Safety legend:
  - **READ** - does not modify the device. Safe.
  - **WRITE** - modifies flash. Can brick the phone. Make a full backup first.
  - **CONTROL** - changes device state (reboot / active slot).
  - **ADVANCED** - low-level memory/fuse access; may be blocked by secure boot.

> Before running ANY WRITE/erase command, make a verified full backup
> (`scripts/backup.sh`) and copy it somewhere safe.

## What this loader advertises

When `edl` connects, the loader reports **23 supported firehose functions**:

```
program            verifysignature   read              nop
patch              configure         setbootablestoragedrive
erase              power             firmwarewrite     getstorageinfo
emmc               ufs               fixgpt            eMMCinfo
programsecure      readsecure        getversion        readSerialNum
getcpuid           bootprotect       getSecureBootStatus  getboot1status
```

Storage is **eMMC, 512-byte sectors, ~29.12 GiB (61,079,552 sectors)**, with an
**A/B slot** layout (partitions suffixed `_a` / `_b`).

---

## Capability matrix

| Capability | Safety | `edl` command | Firehose function(s) |
|---|---|---|---|
| Device identity (HWID, serial, PK hash) | READ | shown automatically at connect | `getversion`, `readSerialNum`, `getcpuid` |
| Secure-boot status | READ | `secureboot` | `getSecureBootStatus`, `bootprotect`, `getboot1status` |
| Storage / flash info | READ | `getstorageinfo` | `getstorageinfo`, `eMMCinfo`, `emmc` |
| Partition table (print) | READ | `printgpt` | `read` |
| Partition table (dump to files) | READ | `gpt <dir>` | `read` |
| Full raw image backup | READ | `rf <file>` | `read` |
| Per-partition backup | READ | `rl <dir>` | `read` |
| Single partition read | READ | `r <name> <file>` | `read` |
| Raw sector read | READ | `rs <start> <count> <file>` | `read` |
| Which slot is active | READ/CONTROL | `getactiveslot` / `setactiveslot` | `setbootablestoragedrive` |
| Flash a partition | WRITE | `w <name> <file>` | `program`, `firmwarewrite` |
| Flash many (from xml dir) | WRITE | `wl <dir>` | `program` |
| Flash whole image | WRITE | `wf <file>` | `program` |
| Write at raw sector | WRITE | `ws <start> <file>` | `program` |
| Erase a partition | WRITE | `e <name>` | `erase` |
| Erase raw sectors | WRITE | `es <start> <count>` | `erase` |
| Set bootable storage/LUN | CONTROL | `setbootablestoragedrive <n>` | `setbootablestoragedrive` |
| Reboot / power off | CONTROL | `reset` | `power` |
| Peek device memory | ADVANCED | `peek` / `peekhex` / `peekdword` | `peek` |
| Poke device memory | ADVANCED | `poke` / `pokehex` / `pokedword` | `poke`, `patch` |
| Dump PBL / QFPROM / memtbl | ADVANCED | `pbl` / `qfp` / `memtbl` | `read`, `peek` |

---

## Details and examples

### Device identity (READ)

HWID, PK hash, and serial are printed by Sahara/firehose during connect - just
run any command (e.g. `printgpt`) and read the header. Observed on this unit:

```
HWID:    0x002980e100420071  (MSM_ID:0x002980e1, OEM_ID:0x0042, MODEL_ID:0x0071)
Serial:  0xa2676da1
Loader build date: May 14 2025
```

### Secure-boot status (READ)

```bash
scripts/edl secureboot --loader=loader/flip-4-edl.bin
```

### Storage / flash info (READ)

```bash
scripts/edl getstorageinfo --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

### Partition table (READ)

Print it:

```bash
scripts/edl printgpt --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

Dump the GPT (and a `rawprogram` xml you can reuse for flashing) to a folder:

```bash
scripts/edl gpt backups/gpt --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

### Backups / reads (READ)

Full raw eMMC image (recommended; also see `scripts/backup.sh`):

```bash
scripts/edl rf backups/flip4-full-emmc.img \
    --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

Every partition to its own file:

```bash
scripts/edl rl backups/partitions \
    --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

A single partition (note A/B suffixes, e.g. `boot_a`, `modem_a`):

```bash
scripts/edl r boot_a backups/boot_a.img \
    --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

Raw sectors (start sector, count, file):

```bash
scripts/edl rs 0 34 backups/first34.img \
    --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

### A/B slot (READ / CONTROL)

```bash
scripts/edl getactiveslot --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
scripts/edl setactiveslot a --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

### Flashing / restore (WRITE - can brick)

> Make a verified backup first. Flashing the wrong image or a bad slot can make
> the phone unbootable.

Restore one partition:

```bash
scripts/edl w boot_a backups/boot_a.img \
    --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

Flash a full raw image back:

```bash
scripts/edl wf backups/flip4-full-emmc.img \
    --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

Flash a set of images using a `rawprogram*.xml` (as produced by `gpt`/`rl`):

```bash
scripts/edl wl backups/partitions \
    --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

### Erase (WRITE - can brick)

```bash
scripts/edl e misc      --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
scripts/edl es 0 34     --loader=loader/flip-4-edl.bin --memory=emmc --skipresponse
```

### Reboot / power (CONTROL)

```bash
scripts/edl reset --loader=loader/flip-4-edl.bin
```

Caveat: on this loader the software reset is unreliable (it needs the read
workaround the `reset` subcommand doesn't expose). The reliable way to leave EDL
mode is to **pull the battery for ~10 seconds and power on**.

### Low-level memory / fuses (ADVANCED)

These read SoC memory/fuses directly and may be limited by secure boot:

```bash
scripts/edl peek 0x100000 0x100 backups/mem.bin --loader=loader/flip-4-edl.bin
scripts/edl pbl backups/pbl.bin  --loader=loader/flip-4-edl.bin
scripts/edl qfp backups/qfprom.bin --loader=loader/flip-4-edl.bin
```

---

## Notes on the "secure" functions

The loader also lists `verifysignature`, `programsecure`, `readsecure`. These
are for signed/secure provisioning flows and are not needed for backup/restore
on this device; they're documented here only for completeness.
