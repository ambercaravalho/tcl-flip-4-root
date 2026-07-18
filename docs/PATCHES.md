# Patches to the vendored `edl` tool

The EDL tool in `third_party/edlclient/` is [bkerler/edl](https://github.com/bkerler/edl)
v3.62, **vendored on purpose** so the fixes below survive and don't have to be
re-applied to a fresh `pip install`. Stock `edl` 3.62 hangs or crashes on the
TCL Flip 4's firehose loader; these three changes make it work.

If you ever re-pull upstream `edl`, you'll need to re-apply the equivalent
changes (or keep using this vendored copy).

## 0. The big one: `--skipresponse` is mandatory

Not a code patch, but the key operational fact: **every read/dump command must
pass `--skipresponse`.**

The Flip 4 loader does not emit the XML `<response value="ACK" .../>` tag that
`edl` waits for before reading raw data. Without `--skipresponse`, `edl` blocks
forever at:

```
firehose - Trying to read first storage sector...
```

With `--skipresponse`, `edl` skips waiting for that tag and reads the raw payload
directly, which is what this loader sends.

## 1. `TypeError` on the read ACK check

File: `third_party/edlclient/Library/firehose.py` (in `cmd_read_buffer`)

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

## 2. Infinite USB retry loop (the "hang")

File: `third_party/edlclient/Library/Connection/usblib.py` (in `usbread`)

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

File: `third_party/edlclient/Library/firehose.py` (in `cmd_read` and `cmd_read_buffer`)

Both raw-read loops decremented "bytes remaining" only when data arrived, so a
stalled device meant an endless loop of zero-length reads. Each loop now aborts
after 5 consecutive empty reads, so a stall fails fast with a clear message
instead of hanging.

---

These changes are read-path only. They make failures bounded and correct; they
do not alter what data is read from the device.
