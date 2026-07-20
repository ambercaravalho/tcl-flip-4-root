# Patches to the vendored `edl` tool

> **Experimental / use at your own risk.** This is unofficial reverse-engineering
> notes for one specific phone. EDL writes can **permanently brick** your device.
> Do your own research and **always make a full, verified backup first**
> (`scripts/backup.sh`). See the [README](../README.md).

The EDL tool in `vendor/edlclient/` is [bkerler/edl](https://github.com/bkerler/edl)
v3.62, **vendored on purpose** so the fixes below survive and don't have to be
re-applied to a fresh `pip install`. Stock `edl` 3.62 hangs or crashes on the
TCL Flip 4's firehose loader; the one operational rule plus four code fixes
below make it work.

If you ever re-pull upstream `edl`, you'll need to re-apply the equivalent
changes (or keep using this vendored copy).

## 0. The big one: `--skipresponse` on READS only, never on WRITES

Not a code patch, but the single most important operational fact:

- **READ / dump commands (`r`, `rs`, `printgpt`): pass `--skipresponse`.**
- **WRITE commands (`w`, `ws`): do NOT pass `--skipresponse`.**

### Reads need it

The Flip 4 loader does not emit the XML `<response value="ACK" .../>` tag that
`edl` waits for before reading raw data. Without `--skipresponse`, `edl` blocks
forever at:

```
firehose - Trying to read first storage sector...
```

With `--skipresponse`, `edl` skips waiting for that tag and reads the raw payload
directly, which is what this loader sends.

### Writes must NOT use it (or they silently do nothing)

For a `program` (write), the loader *does* use the handshake: it replies to the
`<program .../>` header with a "ready for raw data" response, and only **commits
the write** if that handshake is completed. With `--skipresponse`, `edl` skips
reading that reply, streams the payload anyway, and prints:

```
Wrote <file> to sector <n>.
```

...but the data is **never persisted** - a fresh-session read-back returns the
original stock bytes - and the stale, unread reply desyncs the protocol so the
next command dies with `KeyError: 2` and then `Sahara error state`.

The fix is purely operational: run writes **without** `--skipresponse` (the
`<program>` handshake completes, the write commits), then read back **with**
`--skipresponse` and compare sha256 before rebooting. Verified: a
no-`--skipresponse` write of `vbmeta_b`/`odm_b` reads back byte-for-byte equal to
the patched image; the `--skipresponse` version reads back as stock.

## 1. `TypeError` on the read ACK check

File: `vendor/edlclient/Library/firehose.py` (in `cmd_read_buffer`)

`xmlsend()` returns a `response` whose `.data` is sometimes a parsed `dict` and
sometimes raw `bytes`. The original code assumed `dict`:

```python
# before
if "value" in rsp.data and rsp.data["value"] == "NAK":
```

When `.data` was `bytes`, `"value" in rsp.data` raised
`TypeError: a bytes-like object is required, not 'str'` and the whole dump
crashed. Fixed by guarding the type:

```python
# after
if isinstance(rsp.data, dict) and rsp.data.get("value") == "NAK":
```

> This exact error, and the pointer toward its fix, is documented in Ryjelsum's
> writeup: [*Continuing my Qualcomm garbage addiction: QM215 KaiOS flip phones*](https://ryjelsum.me/homelab/qm215-kaios-flips/).

## 2. Infinite USB retry loop (the "hang")

File: `vendor/edlclient/Library/Connection/usblib.py` (in `usbread`)

The timeout-retry logic compared the timeout *value* to `10`:

```python
# before
if "timed out" in error:
    if timeout is None:
        return b""
    if timeout == 10:      # timeout holds milliseconds (e.g. 1000), never == 10
        return b""
    timeout += 1           # so this just grows forever
```

Because `timeout` is in milliseconds (default 1000), `timeout == 10` was never
true, so a silent device caused an infinite retry loop. Replaced with a bounded
retry counter and a forced-finite timeout (a `None` timeout can make libusb
block indefinitely):

```python
# after
if timeout is None:
    timeout = self.timeout or 1000
...
if "timed out" in error:
    timeouts += 1
    if timeouts >= 10:
        break
    continue
```

## 3. Read loops could spin forever on empty reads

File: `vendor/edlclient/Library/firehose.py` (in `cmd_read` and `cmd_read_buffer`)

Both raw-read loops decremented "bytes remaining" only when data arrived, so a
stalled device meant an endless loop of zero-length reads. Each loop now aborts
after 5 consecutive empty reads, so a stall fails fast with a clear message
instead of hanging.

## 4. `KeyError: 2` when the loader returns no `<response value=...>`

File: `vendor/edlclient/Library/firehose.py` (in `cmd_read_buffer`)

After a raw read, `cmd_read_buffer` inspects the trailing response. When the
loader returns no standard `<response value="ACK"/>` (common on this loader,
especially right after a write handshake), the original code blindly indexed
`rsp[2]`:

```python
# before
else:
    if len(rsp) > 1:
        if b"Failed to open the UFS Device" in rsp[2]:
            self.error(f"Error:{rsp[2]}")
        self.lasterror = rsp[2]
    return response(resp=False, data=resData, error=rsp[2])   # KeyError: 2
...
return response(resp=resp, data=resData, error=rsp[2])        # also KeyError
```

`rsp` is a dict that often has neither `"value"` nor an integer key `2`, so this
raised `KeyError: 2` and aborted the dump. Fixed by guarding every `rsp[2]`
access and, when there is no standard response, trusting the raw bytes already
read (a full-length read is treated as success):

```python
# after
else:
    err = rsp[2] if (isinstance(rsp, dict) and 2 in rsp) else info
    if isinstance(err, bytes) and b"Failed to open the UFS Device" in err:
        self.error(f"Error:{err}")
    got_all = bytestoread <= 0
    if not got_all:
        self.lasterror = err
    return response(resp=got_all, data=resData, error=err)
errval = rsp[2] if (isinstance(rsp, dict) and 2 in rsp) else info
...
return response(resp=resp, data=resData, error=errval)
```

---

These changes are read-path only. They make failures bounded and correct; they
do not alter what data is read from the device.
