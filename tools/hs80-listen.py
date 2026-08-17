#!/usr/bin/env python3
"""Passive HID listener for the Corsair HS80 physical controls.

Reverse-engineering the volume wheel, mic-mute button, and dial means watching
the reports the device sends when you touch them. This tool ONLY reads — it
never writes to the device, so it cannot upset the dongle the way the vendor
probe can.

It reads every HS80 hidraw node at once and prints each report as it arrives,
tagged with its report id, so you can correlate a physical action with its
bytes:

  - report 0x0e  (hidraw2, consumer): volume up/down, mic mute
  - report 0x21 / 0x11 (hidraw2, keyboard): media keys mapped as keys
  - report 0x22  (hidraw5, mouse):   dial / buttons / wheel

Usage:  python3 hs80-listen.py
        # then: spin the volume wheel, tap mic-mute, turn the dial, etc.
        # Ctrl-C to stop.
"""

import os
import select
import sys
import time

VENDOR_ID = 0x1B1C
PRODUCT_ID = 0x0A6B


def find_nodes():
    base = "/sys/class/hidraw"
    nodes = []
    for entry in sorted(os.listdir(base)):
        dev = os.path.join(base, entry, "device")
        try:
            with open(os.path.join(dev, "uevent")) as f:
                ue = f.read().lower()
        except OSError:
            continue
        if f"{VENDOR_ID:08x}" in ue and f"{PRODUCT_ID:08x}" in ue:
            try:
                sz = os.path.getsize(os.path.join(dev, "report_descriptor"))
            except OSError:
                sz = 0
            nodes.append((f"/dev/{entry}", sz))
    return nodes


def main():
    nodes = find_nodes()
    if not nodes:
        sys.exit("No HS80 hidraw nodes found (dongle unplugged?)")

    fds = {}
    for path, sz in nodes:
        try:
            fds[os.open(path, os.O_RDONLY | os.O_NONBLOCK)] = (path, sz)
        except OSError as e:
            print(f"# could not open {path}: {e}")
    if not fds:
        sys.exit("Could not open any HS80 node (permissions? see the udev rule)")

    for fd, (path, sz) in fds.items():
        print(f"# listening on {path} (descriptor {sz} bytes)")
    print("# work the volume wheel / mic-mute / dial; Ctrl-C to stop\n")

    last = 0.0
    try:
        while True:
            r, _, _ = select.select(list(fds), [], [], 1.0)
            for fd in r:
                data = os.read(fd, 64)
                if not data:
                    continue
                path = fds[fd][0]
                # trim trailing zeros for readability, keep at least 8 bytes
                trimmed = data.rstrip(b"\x00")
                shown = data[:max(8, len(trimmed))]
                gap = ""
                now = time.monotonic()
                if last:
                    gap = f" (+{now - last:5.2f}s)"
                last = now
                rid = data[0] if data else 0
                print(f"{path}  id=0x{rid:02x}{gap}  "
                      f"{' '.join(f'{b:02x}' for b in shown)}")
    except KeyboardInterrupt:
        print("\n# stopped")
    finally:
        for fd in fds:
            os.close(fd)


if __name__ == "__main__":
    main()
