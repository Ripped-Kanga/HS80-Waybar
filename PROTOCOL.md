# Corsair HS80 RGB Wireless — HID protocol notes

Reverse-engineering notes for the wireless dongle (USB `1b1c:0a6b`). These
back the `hs80-battery` poller and document what else the device exposes, so a
future feature (mic-mute readout, sidetone, sleep-timeout, etc.) doesn't have
to start from zero.

> **Status:** the property table below has **two verified entries** (battery
> level and the status event id). The full property enumeration is *not*
> complete — the sweep that would have produced it reset the dongle and dropped
> the headset link (see "A warning" at the bottom). Everything here is either
> read straight from the HID report descriptors or verified against a live
> value; nothing is transcribed from memory.

## Interfaces

The dongle enumerates several HID interfaces. Two hidraw nodes carry everything
interesting (node numbers are not stable across replug — match by report
descriptor size / usage page, not by `hidrawN`):

| Node (this session) | USB iface | Descriptor | Role |
|---|---|---|---|
| `/dev/hidraw2` | `…2.4/input3` (`:1.3`) | 267 bytes | Keyboard + consumer + **vendor control** |
| `/dev/hidraw5` | `…2.4/input4` (`:1.4`) | 87 bytes | Mouse-style report (buttons / volume wheel / dial) |

Kernel input mapping (`/proc/bus/input/devices`):

- iface `:1.3` → `event2` (keyboard, has LEDs) plus `event3/4/5` (abs-only nodes)
- iface `:1.4` → `event11` + `js0` + `mouse1`

### hidraw2 report map (from the 267-byte descriptor)

| Report ID | Dir | Usage page | What it is |
|---|---|---|---|
| `0x21` | In/Out | Generic Desktop / Keyboard | Keyboard input + LED output (13-byte array) |
| `0x11` | In/Out | Generic Desktop / Keyboard | Extended keyboard (104 + 8 byte arrays) |
| `0x0e` | In | Consumer | Discrete controls — usages `0xe9`/`0xea` (volume up/down) and `0xe2` (mute). This is the **volume wheel + mic-mute button**, readable with no vendor protocol. |
| `0x0f` | In | Consumer | 16-bit consumer usage code (logical 0–0x3ff). **Note the collision:** consumer *report* `0x0f` is unrelated to vendor *property* `0x0f` (battery). |
| `0x01` | In | Vendor `0xFF42` usage 1 | 63-byte vendor input (command replies + notifications) |
| `0x02` | Out | Vendor `0xFF42` usage 1 | 63-byte vendor output (commands) |
| `0x03` | In | Vendor `0xFF42` usage 2 | 63-byte vendor input — **second input channel, unexplored** |
| `0x58` | In/Out | Vendor `0xFF58` usage 1 | 63-byte vendor in **and** out — **second bidirectional channel, unexplored. Do not write to it blind.** |

### hidraw5 report map (from the 87-byte descriptor)

| Report ID | Dir | What it is |
|---|---|---|
| `0x22` | In | Mouse collection: 32 buttons, 16-bit X/Y, wheel, AC-Pan, plus 5 bytes on vendor page `0xFF00` usage `0xF1`. Exposed to the kernel as `js0` + `mouse1`. Likely where the dial / extra controls surface as relative/button events. |

## Vendor control protocol (report `0x02` out / `0x01` in)

This is Corsair's **BRAGI** protocol. All commands are a 64-byte output report:
byte 0 = report id `0x02`, then the command bytes, zero-padded. Replies are
64-byte input reports with report id `0x01`.

> The descriptor specifies a **63-byte payload** after the report id (64 total).
> The shipped poller happens to write 65 bytes; harmless here, but new code
> should send exactly 64.

### Verified commands

**Property dump — `02 01 00`** (what the shipped poller uses):
```
send:  02 01 00 00 …
reply: 01 f1 00 0f 00 ae 01 00 …
       │  │  │  │  │  └──┴─ value (LE)  0x01ae = 430
       │  │  │  │  └─ pad
       │  │  │  └─ property id 0x0f (battery)   ← poller checks byte[3]
       │  │  └─ 00
       │  └─ f1  (dump/notification marker)
       └─ report id 0x01
```
Battery % = `(byte5 | byte6<<8) / 10` → 430/10 = **43.0%**. Confirmed live.

**Get property — `02 09 <prop_lo> <prop_hi>`** (GET_PROPERTY, opcode `0x09`):
```
send:  02 09 0f 00 00 …
reply: 01 01 0f 00 00 ae 01 00 …
       │  │  │  │  └──┴──┴─ status(00) + value (LE, bytes 5–6) = 430
       │  │  └─ property id 0x0f  ← note: byte[2] here, vs byte[3] in the dump form
       │  └─ 01  (get-property reply marker; dump form uses f1)
       └─ report id 0x01
```
Verified: reading property `0x0f` returned `ae 01` = 430 = 43.0%, matching the
dump form. **This is the clean, addressable way to read a single property.**

**Get property metadata — `02 08 <prop_lo> <prop_hi>`** (opcode `0x08`):
```
send:  02 08 0f 00 …
reply: 01 00 0f 03 …
       │  │  │  └─ type/width code (0x03 for battery) — meaning not yet pinned down
       │  │  └─ property id 0x0f
       │  └─ 00  (metadata reply marker)
       └─ report id 0x01
```
Returns per-property metadata (a type or width code). Useful for decoding value
widths correctly instead of guessing offsets — but confirm what byte 3 means by
comparing several properties before relying on it.

Confirmed type codes (byte 3 of the `0x08` reply): property `0x0f` (battery) →
`0x03`; property `0x10` (status) → `0x04`. Observed (2026-08-17): while the
telemetry was **wedged** (see below), metadata reads (`0x08`) still answered
while value reads (`0x09`) returned nothing — so `0x08` is served from the
dongle's static cache and does not prove the headset is reachable. Do **not**
read this as a "headset asleep" signal: in the observed case the headset was on
and playing audio the whole time; the value reads failed because probing had
wedged the telemetry, not because the headset was off.

### Opcodes that produced no reply
`0x02` and `0x0a` returned nothing. **`0x0a` was in the command sequence
immediately before the dongle reset — treat it as suspect and do not send it.**

### Property table

| Property | Meaning | Value encoding | Status |
|---|---|---|---|
| `0x0f` | Battery level | 16-bit LE deci-percent (÷10) | **Verified** (43.0%) |
| `0x10` | Battery / connection status | — | Type code `0x04` (from `0x08`); a status/charge field. Value semantics **not decoded** — see note below |

Charge/status decode is a **dead end via active probing**: reading `0x10` in the
two live states needed to isolate the charging bit reliably wedges the telemetry
(observed twice). The realistic path is an **iCUE USB capture on Windows** — iCUE
reads and writes these properties routinely, and a capture would reveal the real
command sequence *including whatever session/subscription handshake the dongle
expects first*. That missing init step is the likely reason bare property reads
destabilise the channel, and it's the prerequisite for any read/write of status,
sidetone, EQ, sleep-timeout, or RGB.

Every other property id is **unknown** — the enumeration sweep did not complete.
For a starting list of candidate BRAGI property ids, consult the OpenRGB and
ckb-next Bragi controller sources rather than trusting an unverified table here.

## What we still can't do from software alone

- **Consumer report `0x0e`** (volume/mute) and **`0x22`** (dial/buttons) only
  emit on physical interaction. Capturing them needs someone at the keyboard —
  see `tools/hs80-listen.py`.
- Vendor channels **`0x03`** and **`0x58`** are completely unexplored.

## Tools

- `tools/hs80-probe.py` — paced GET_PROPERTY / metadata sweep (ops `0x08`/`0x09`
  only, `0x50` cap, aborts on error). **⚠️ Even this wedges the battery telemetry
  in practice** (it recovers on its own in minutes, audio unaffected). Do not run
  it against a headset you're using; the vendor channel is too fragile for
  routine probing without the iCUE handshake described above.
- `tools/hs80-listen.py` — **write-free** passive reader for the consumer
  (`0x0e`) and mouse/dial (`0x22`) reports. This is the *safe* tool — it never
  writes to the device, so it cannot wedge anything. Run it, then work the volume
  wheel / mic-mute / dial to map the byte layout. This is the recommended next
  expansion (e.g. a mic-mute indicator).

## A warning (why the sweep is unfinished)

During this session, active probing on the `0x02` vendor channel repeatedly
**wedged the battery telemetry** — the dongle stops answering property/battery
reads and emits reconnect events (`0xa6`) instead. The first, most aggressive
sweep also triggered a one-off **USB re-enumeration** of the dongle; later,
gentler probing wedged the telemetry *without* any re-enumeration. Throughout
all of it, **audio, the RF link, and the headset's own battery LED kept working
normally** — only the host-side battery *reporting* breaks. (An earlier draft of
this doc claimed the wireless link dropped and the headset needed its power
button; that was wrong — the link never dropped.)

The exact trigger is not confirmed — candidates are the unknown opcode `0x0a`,
out-of-range property ids (`0xfe`/`0xff`), or command pacing — and it recurred
even with paced, in-range, read-only commands, so **treat the whole channel as
too fragile to probe on a headset you're using.**

This vendor endpoint shares a channel with handle/flash commands. **Never sweep
raw opcodes on report `0x02`.** Enumerate with `0x08`/`0x09` only, pace commands
(≥200 ms), keep property ids in range, and stop on the first error.

### Aftermath / recovery (2026-08-17)

After the reset the device was **not bricked** (still `1b1c:0a6b`, USB audio
kept working the whole time — audio and the HID control endpoint are separate
interfaces, so a wedged control channel does not affect sound). But the
dongle's telemetry desynced from the headset:

- the `02 01 00` dump returned event id **`0xa6`** (a reconnect/status event),
  not the battery event `0x0f`, so the shipped poller (which only accepts
  `0x0f`) reported "not connected";
- reading property `0x0f` returned `01 00` at the value offset (both `0x0f` and
  `0x10` returned the identical `01 00` — likely a "property unavailable"
  sentinel, not a real 0.1% reading);
- the control channel answered only intermittently.

A cold power-cycle of the dongle (physical unplug ~10 s, replug on a different
port) did **not** clear it — the frozen values returned identically after a
clean re-enumeration, so the stuck state is **headset-side or a pairing/mode
state**, not volatile dongle state.

**LED, corrected (per the official QSG, `49_002222_AC_NA_HS80_RGB_WIRELESS_QSG`):**
the headset status LED *normally* blinks its battery level when running on
battery — **RED = low, ORANGE = medium, GREEN = high** (it pulses while
charging, solid green when full). So a flashing orange/green headset LED is a
**medium-to-high battery indication, not a fault** — consistent with the ~43%
read earlier. The earlier "flashing = low-battery warning" note was wrong. The
dongle LED is the pairing indicator: solid white = connected/normal, rapid blink
= can't reach headset, persistent red blink = **re-pair via iCUE** (Windows-only
— a real constraint on Linux).

The remaining fault is narrow: **battery telemetry over the HID channel is not
being reported to the host** (dump emits event `0xa6`, property reads the
unavailable sentinel), while audio, the RF link, and the headset's own battery
LED are all fine.

**Recovery (observed twice):** the wedge **self-heals within a few minutes** on
its own — the headset pushes its next battery update and telemetry repopulates.
No physical intervention was needed or helped: the cold dongle replug did
nothing, and power-cycling the headset did nothing (both incidents recovered on
their own timeline regardless). The reliable trigger for a fresh report, if you
don't want to wait, is a genuine **charge-state change** (plug in / unplug the
charge cable), which forces the headset to send an updated status.

**This means active probing of property `0x10` is a dead end for decoding charge
status:** every attempt to read it reliably wedges the very telemetry being
measured. The realistic path to the status/charge encoding is an iCUE USB
capture on Windows (see below), not more probing here.
