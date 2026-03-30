#!/usr/bin/env python3
"""Waybar module for Corsair HS80 RGB Wireless battery status."""

import json
import os

VENDOR_ID = 0x1B1C
PRODUCT_ID = 0x0A6B
BATTERY_CMD = [0x02, 0x01, 0x00]
BATTERY_EVENT = 0x0F


def find_hidraw_paths():
    """Find hidraw devices matching the HS80 VID/PID."""
    paths = []
    base = "/sys/class/hidraw"
    if not os.path.isdir(base):
        return paths

    for entry in os.listdir(base):
        uevent_path = os.path.join(base, entry, "device", "uevent")
        try:
            with open(uevent_path) as f:
                content = f.read()
            # Match HID_ID line: HID_ID=0003:00001B1C:00000A6B
            for line in content.splitlines():
                if line.startswith("HID_ID="):
                    parts = line.split(":")
                    if len(parts) == 3:
                        vid = int(parts[1], 16)
                        pid = int(parts[2], 16)
                        if vid == VENDOR_ID and pid == PRODUCT_ID:
                            paths.append(f"/dev/{entry}")
        except (OSError, ValueError):
            continue

    paths.sort()
    return paths


def get_battery():
    """Try to read battery from HS80 via HID."""
    import hid

    paths = find_hidraw_paths()
    if not paths:
        return None

    for path in paths:
        try:
            h = hid.device()
            h.open_path(path.encode())
            try:
                h.write(BATTERY_CMD + [0] * 62)
                # Try a few reads in case first response is not battery
                for _ in range(5):
                    data = h.read(65, timeout_ms=500)
                    if data and data[3] == BATTERY_EVENT:
                        pct = (data[5] | (data[6] << 8)) / 10
                        if 0 <= pct <= 100:
                            return pct
            finally:
                h.close()
        except Exception:
            continue

    return None


def get_icon(pct):
    if pct >= 80:
        return "󰥂"
    if pct >= 60:
        return "󰥁"
    if pct >= 40:
        return "󰥀"
    if pct >= 20:
        return "󰤿"
    return "󰤾"


def get_css_class(pct):
    if pct <= 15:
        return "critical"
    if pct <= 30:
        return "low"
    return "normal"


def main():
    pct = get_battery()

    if pct is not None:
        icon = get_icon(pct)
        output = {
            "text": f"{icon} {pct:.0f}%",
            "tooltip": f"Corsair HS80 Battery: {pct:.0f}%",
            "class": get_css_class(pct),
        }
    else:
        output = {
            "text": "󰋎 --",
            "tooltip": "Corsair HS80: not connected",
            "class": "unavailable",
        }

    print(json.dumps(output))


if __name__ == "__main__":
    main()