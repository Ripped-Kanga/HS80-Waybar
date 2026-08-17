#!/usr/bin/env python3
"""Read-only capture of the HS80 physical controls (mic-mute, volume, dial).

SAFE: opens the hidraw nodes O_RDONLY and never writes to the device, so it
cannot disturb the vendor/battery channel. It just watches the reports the
headset sends when you touch a control.

Run it, then during the ~35 s window:
  1. Flip the mic boom UP   (mute)   — pause a second
  2. Flip the mic boom DOWN (unmute) — pause a second
  3. Repeat the flip once more
  4. Roll the volume wheel UP a little, then DOWN

At the end it prints every distinct control frame it saw, decoded.

Usage:  python3 hs80-capture-controls.py [seconds]
"""

import os
import select
import sys
import time

VENDOR_ID = 0x1B1C
PRODUCT_ID = 0x0A6B
DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 35.0


def hs80_nodes():
    base = "/sys/class/hidraw"
    out = []
    for entry in sorted(os.listdir(base)):
        dev = os.path.join(base, entry, "device")
        try:
            ue = open(os.path.join(dev, "uevent")).read().lower()
        except OSError:
            continue
        if f"{VENDOR_ID:08x}" in ue and f"{PRODUCT_ID:08x}" in ue:
            out.append(f"/dev/{entry}")
    return out


def decode(data):
    rid = data[0]
    if rid == 0x0E and len(data) >= 2:
        b = data[1]
        bits = []
        if b & 0x01:
            bits.append("VOL+")
        if b & 0x02:
            bits.append("VOL-")
        if b & 0x04:
            bits.append("MUTE")
        return f"consumer 0x0e  data=0x{b:02x}  [{' '.join(bits) or 'released/none'}]"
    if rid in (0x21, 0x11):
        return f"keyboard 0x{rid:02x}  {' '.join(f'{x:02x}' for x in data[1:9])}"
    if rid == 0x22:
        return f"mouse/dial 0x22  {' '.join(f'{x:02x}' for x in data[1:10])}"
    if rid == 0x01:
        return None  # battery/vendor reply from the bar poll — ignore
    return f"report 0x{rid:02x}  {' '.join(f'{x:02x}' for x in data[1:10])}"


def main():
    nodes = hs80_nodes()
    fds = {}
    for p in nodes:
        try:
            fds[os.open(p, os.O_RDONLY | os.O_NONBLOCK)] = p
        except OSError as e:
            print(f"# could not open {p}: {e}")
    if not fds:
        sys.exit("No HS80 hidraw nodes (dongle unplugged?)")

    print(f"# capturing for {DURATION:.0f}s on {', '.join(nodes)}")
    print("# NOW: flip mic UP (mute), pause, flip DOWN (unmute), repeat; "
          "then roll volume up/down\n")

    seen = {}   # decoded-string -> first elapsed time
    start = time.monotonic()
    end = start + DURATION
    while time.monotonic() < end:
        r, _, _ = select.select(list(fds), [], [], min(1.0, end - time.monotonic()))
        for fd in r:
            try:
                data = os.read(fd, 64)
            except OSError:
                continue
            if not data:
                continue
            dec = decode(data)
            if dec is None:
                continue
            t = time.monotonic() - start
            print(f"  t={t:5.1f}s  {fds[fd]}  {dec}")
            seen.setdefault(dec, t)

    for fd in fds:
        os.close(fd)

    print("\n=== distinct control frames seen ===")
    if not seen:
        print("  (nothing — the control may not report over HID, "
              "or no action was captured)")
    for dec, t in sorted(seen.items(), key=lambda kv: kv[1]):
        print(f"  first@{t:5.1f}s  {dec}")


if __name__ == "__main__":
    main()
