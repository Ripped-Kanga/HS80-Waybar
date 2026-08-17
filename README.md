# hs80-battery
Battery level for the Corsair HS80 RGB Wireless headset in your status bar, made with Claude Code.

Works two ways:
- **Omarchy 4** shell plugin (the Quickshell-based bar that replaced Waybar)
- **Waybar** custom module (Omarchy 3 and earlier, or any other Waybar setup)

The battery is read directly from the wireless dongle over hidraw — no `python-hid`, no iCUE, no daemons. Just Python's standard library.

![HS80-Battery-Icon-Waybar](waybar-hs80-battery.png)

# Device access (required for both setups)

Reading the dongle needs access to its `/dev/hidraw*` node. Install the bundled udev rule once:

```
sudo cp 71-corsair-hs80.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger
```

# Omarchy 4 plugin

Install and enable straight from this repo:

```
omarchy plugin add https://github.com/Ripped-Kanga/hs80-battery --enable
```

The widget lands in the right section of the bar, showing a battery glyph and percentage. It dims when the headset is powered off, shows `…` while the dongle is re-establishing the link, shifts toward the theme's urgent colour when the battery is low (≤30%), and goes fully urgent when critical (≤15%). Colours follow your Omarchy theme automatically.

A **mic-muted glyph** () appears in front of the battery when you flip the mic boom up to mute, and disappears when you flip it down. This is tracked live by a small read-only listener (`bin/hs80-mic-listen`) that watches the headset's mic-mute notifications without ever writing to the device. Note: the mute state is only known after the first flip since the headset powered on, so the glyph won't show until you've muted at least once.

- **Left click** the widget to refresh immediately.
- **Move it**: `omarchy bar move ripped-kanga.hs80-battery --section center`
- **Refresh from a script**: `omarchy-shell ripped-kanga.hs80-battery refresh`

## Settings

Tune the widget in the `bar.layout` entry in `~/.config/omarchy/shell.json` (hot-reloads on save):

```jsonc
{
  "id": "ripped-kanga.hs80-battery",
  "interval": 60,                 // poll interval in seconds (min 10)
  "hideWhenDisconnected": false   // true = hide widget when the headset is off
}
```

# Waybar (legacy)

Copy `bin/hs80-battery` into a folder of your choosing, I used `.config/waybar/scripts`.

In your Waybar config.jsonc file, add this entry:

```
  "custom/hs80_battery_headset": {
    "exec": "~/.config/waybar/scripts/hs80-battery",
    "return-type": "json",
    "interval": 60,
    "format": "{}",
    "tooltip": true
  },
```

Add the custom entry to one of your modules.

```
  "modules-right": [
    "group/tray-expander",
    ...

    "custom/hs80_battery_headset",

    ...
    "cpu",
    "battery"
  ],
```

In your Waybar style.css, add this or style to your preference.

```
#custom-hs80_battery_headset.normal {
    color: #a6e3a1;
}
#custom-hs80_battery_headset.low {
    color: #f9e2af;
}
#custom-hs80_battery_headset.critical {
    color: #f38ba8;
}
#custom-hs80_battery_headset.reconnecting {
    color: #89b4fa;
}
#custom-hs80_battery_headset.unavailable {
    color: #585b70;
}
```

Reload Waybar.

> `hs80-battery.py` is the original script and still works, but it needs the `python-hid` package. `bin/hs80-battery` is a drop-in replacement with no dependencies.

# Protocol notes & tools

The dongle's HID protocol (Corsair's BRAGI vendor channel) is documented in [`PROTOCOL.md`](PROTOCOL.md): the command framing, the `GET_PROPERTY` read used for battery, the full report map for both interfaces, and the surfaces not yet explored (mic-mute/volume, the dial, and two unmapped vendor channels).

Two read-mostly helpers live in `tools/`:
- `hs80-probe.py` — a safe, paced, read-only sweep of the vendor properties.
- `hs80-listen.py` — a passive listener for the physical controls (volume wheel, mic-mute, dial).

> ⚠️ Do not send arbitrary commands to the `0x02` vendor channel. Aggressive probing once reset the dongle and briefly wedged its battery telemetry (audio was unaffected). See the warning in `PROTOCOL.md`.
