# HS80-Waybar
A small python script to display the battery level of the Corsair HS80 Gaming headset in Waybar, made with Claude Code.

# Setup
Copy the `hs80-battery.py' into a folder of your choosing, I used '.config/waybar/scripts'.

In your Waybar config.jsonc file, add this module:

```
  "custom/hs80_battery_headset": {
    "exec": "~/.config/waybar/scripts/hs80-battery.py",
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

Reload Waybar.
