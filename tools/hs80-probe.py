#!/usr/bin/env python3
"""Safe, paced BRAGI property sweep for the Corsair HS80 wireless dongle.

Enumerates readable vendor properties on the control interface (report 0x02 out
/ 0x01 in) using GET_PROPERTY (0x09) and metadata (0x08) ONLY. Prints a table of
every property that answers.

  READ-ONLY. It never sets a property and never sends any opcode other than
  0x08/0x09. Do not add opcodes to the sweep — the flash/handle command family
  lives on this same channel.

CAUTION: an earlier, unpaced version of this sweep reset the dongle and dropped
the headset link. This version paces commands, caps the property range, guards
every frame index, and aborts on the first I/O error or link drop. It has NOT
been re-validated since that reset. If the headset goes quiet mid-run, stop and
power-cycle the headset (physical power button); replug the dongle if the vendor
channel is still silent.

Usage:  python3 hs80-probe.py            # sweep 0x00..0x50
        python3 hs80-probe.py 0x00 0x30  # custom (inclusive) range, still <=0x50
"""

import os
import select
import sys
import time

VENDOR_ID = 0x1B1C
PRODUCT_ID = 0x0A6B
REPORT_OUT = 0x02          # vendor output report id
OP_GET = 0x09              # GET_PROPERTY (returns value)
OP_META = 0x08            # get metadata (returns type/width code)
BATTERY_PROP = 0x0F
CMD_GAP_S = 0.20           # >=200ms between commands
FRAME_WAIT_S = 0.5         # wait for first reply frame
FRAME_GRACE_S = 0.08       # extra window to catch multi-frame replies
PROP_CAP = 0x50            # never sweep beyond this


def find_control_node():
    """Return the hidraw path whose report descriptor is the 267-byte control
    interface (the one carrying the FF42 vendor collection)."""
    base = "/sys/class/hidraw"
    best = None
    for entry in sorted(os.listdir(base)):
        dev = os.path.join(base, entry, "device")
        try:
            with open(os.path.join(dev, "uevent")) as f:
                ue = f.read()
        except OSError:
            continue
        if f"{VENDOR_ID:08X}".lower() not in ue.lower():
            continue
        if f"{PRODUCT_ID:08X}".lower() not in ue.lower():
            continue
        try:
            sz = os.path.getsize(os.path.join(dev, "report_descriptor"))
        except OSError:
            sz = 0
        # 267-byte descriptor is the vendor/control interface
        if sz > 200:
            return f"/dev/{entry}"
        best = best or f"/dev/{entry}"
    return best


def frames_for(fd, prop, want_marker):
    """Send a query and return the first reply frame that matches `prop`.

    want_marker: 0x01 for GET_PROPERTY replies, 0x00 for metadata replies.
    Every index is length-guarded; `f1` dump frames are ignored (they belong to
    another reader's 02 01 00 poll, e.g. the bar widget)."""
    # drain stale input
    while True:
        r, _, _ = select.select([fd], [], [], 0.03)
        if not r:
            break
        try:
            os.read(fd, 64)
        except OSError:
            raise

    op = OP_META if want_marker == 0x00 else OP_GET
    os.write(fd, bytes([REPORT_OUT, op, prop & 0xFF, (prop >> 8) & 0xFF]
                       + [0] * 60))

    match = None
    deadline = time.time() + FRAME_WAIT_S
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], max(0, deadline - time.time()))
        if not r:
            continue
        data = os.read(fd, 64)                 # raises OSError on link loss
        if len(data) < 4:
            continue
        if data[1] == 0xF1:                    # unsolicited dump — ignore
            continue
        if data[1] == want_marker and data[2] == prop and match is None:
            match = data
        deadline = time.time() + FRAME_GRACE_S  # grace after any frame
    return match


def read_battery(fd):
    m = frames_for(fd, BATTERY_PROP, want_marker=0x01)
    if m is None or len(m) < 7:
        return None
    return (m[5] | (m[6] << 8)) / 10


def hx(b, n=16):
    return " ".join(f"{x:02x}" for x in b[:n])


def main():
    lo, hi = 0x00, PROP_CAP
    if len(sys.argv) == 3:
        lo, hi = int(sys.argv[1], 0), int(sys.argv[2], 0)
    hi = min(hi, PROP_CAP)

    path = find_control_node()
    if not path:
        sys.exit("HS80 control interface not found (dongle unplugged?)")
    print(f"# control node: {path}")

    fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    try:
        b0 = read_battery(fd)
        if b0 is None:
            sys.exit("# no battery reply — headset link is down. Power-cycle "
                     "the headset before probing.")
        print(f"# battery at start: {b0}%  (link up)")

        # negative control: an in-range id we don't expect to exist
        time.sleep(CMD_GAP_S)
        nc = frames_for(fd, 0x4E, want_marker=0x01)
        print(f"# negative control 0x4e: "
              f"{hx(nc) if nc is not None else 'no reply'}")

        print(f"# sweeping properties 0x{lo:02x}..0x{hi:02x} "
              f"(GET_PROPERTY + metadata)\n")
        print(f"{'prop':>5}  {'meta(0x08)':<24}  value(0x09)")
        found = 0
        for prop in range(lo, hi + 1):
            try:
                time.sleep(CMD_GAP_S)
                meta = frames_for(fd, prop, want_marker=0x00)
                time.sleep(CMD_GAP_S)
                val = frames_for(fd, prop, want_marker=0x01)
            except OSError as e:
                print(f"\n# I/O error at prop 0x{prop:02x} ({e}); aborting. "
                      "The dongle may have reset — power-cycle the headset.")
                break
            if meta is None and val is None:
                continue
            found += 1
            print(f" 0x{prop:02x}  {hx(meta, 6) if meta is not None else '-':<24}  "
                  f"{hx(val) if val is not None else '-'}")

            # link-drop guard every 8 hits
            if found % 8 == 0:
                time.sleep(CMD_GAP_S)
                if read_battery(fd) is None:
                    print("\n# battery read failed mid-sweep — link dropped; "
                          "aborting.")
                    break

        b1 = read_battery(fd)
        print(f"\n# battery at end: {b1}%  (start {b0}%)")
        print(f"# responsive properties: {found}")
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
