# KompleteSynthesia-win

**Windows 11 Python bridge for Synthesia and the Native Instruments Komplete Kontrol S61 MK2.**

This is an **early hardware-testing prototype**, not a verified turnkey solution.
The Light Guide can run directly from Python, while the two 480x272 keyboard
screens are driven through a tiny Rust helper using the existing `encdr` crate.
Synthesia MIDI parsing, capture, scaling, configuration, and application logic
are Python. No USB driver replacements or Zadig are intended.

## Features in this first milestone

- Synthesia's *Finger-based channel* note colors on the 61-key Light Guide.
- Synthesia MIDI note-on/note-off and all-notes-off handling.
- 960x272 combined image sent to the keyboard's two displays through Encdr.
- Screen test pattern for isolating hardware problems from capture problems.
- Captures the **visible** Windows client area of Synthesia; `fit`, `fill`, and
  `stretch` layouts. A covered or minimized window cannot be mirrored reliably.
- Logs hardware button and encoder events; playback mappings are **not yet** enabled.
- MIDI Services native loopback support without requiring LoopBe1.

## Requirements

- Windows 11, 64-bit Python 3.11+ (tested in CI, not yet with physical hardware).
- Native Instruments S61 MK2 (`17cc:1620`), connected and powered.
- Synthesia for Windows.
- For screens, Native Instruments driver/background hardware services installed;
  Encdr's Windows service route must successfully communicate with the keyboard.
- Windows MIDI Services with a built-in app loopback **or** any compatible MIDI
  loopback; the application **does not create a virtual MIDI device** itself.

## Installation

```powershell
git clone https://github.com/horse5g/KompleteSynthesia-win.git
cd KompleteSynthesia-win
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For the screens, use the `KompleteSynthesia-win-W11` artifact from GitHub Actions
and copy `bin/encdr_bridge.exe` into this repository's `bin/` folder, **or**
build the native helper locally (Rust and MSVC C++ build tools required):

```powershell
cargo build --release --manifest-path native/encdr_bridge/Cargo.toml
```

The light-only mode below **does not require Rust or the helper binary**.

## Windows MIDI Services setup (no LoopBe1 required)

For supported Windows 11 versions, Windows MIDI Services includes a default
application loopback with two ends, **Default App Loopback (A)** and **(B)**.
Confirm availability on your PC in Windows MIDI Settings or with `--list-midi`.

1. In **Synthesia → Settings → Music Devices**, select
   **Default App Loopback (A)** as a MIDI output.
2. Enable **Key Lights → Finger-based channel** for that output.
3. Receive on **Default App Loopback (B)** in this app. The two ends are
   paired; sending to one is received at the other.
4. If the built-in loopback isn't exposed on your Windows build, configure a
   Windows MIDI Services developer loopback or another virtual MIDI port, then
   provide the exact receiving port with `--midi-port`.

> Note: Windows MIDI Services and the user-facing loopback setup tools have
> different release schedules. The Python MIDI backend **cannot create** a
> virtual input port on Windows using `mido`/`python-rtmidi` alone.

## First test: Light Guide only

```powershell
python -m kompletesynthesia --list-midi
python -m kompletesynthesia --light-only --midi-port "Default App Loopback (B)"
```

This opens the S61 MK2 HID interface directly and does not use Encdr.
**Do not run the light-only mode alongside the screen bridge** because both
may claim the keyboard's HID interface. Confirm lighting follows the falling
notes and that left/right hands have different colors.

## Second test: hardware screens

```powershell
python -m kompletesynthesia --test-pattern --no-midi
```

Both displays should show `S61 MK2 - LEFT` and `S61 MK2 - RIGHT` on separate
panels. The Light Guide will have a static left/right split. This test isolates
Encdr's service routing from capture and MIDI. If it fails, capture and MIDI
changes won't fix the underlying display connection.

## Full MVP: screen mirror + Light Guide

Open Synthesia and leave its window visible on the desktop:

```powershell
python -m kompletesynthesia --midi-port "Default App Loopback (B)" --fps 12
```

Switch layouts as desired:

```powershell
python -m kompletesynthesia --capture-mode fill --fps 15
```

`fit` shows the full application with black margins. `fill` crops to the wide
960x272 aspect ratio (may cut off keyboard or controls), while `stretch`
shows everything but distorts proportions. All three modes are provisional;
a dedicated piano-roll crop and per-screen layout are planned.

Press Ctrl+C to stop. The application attempts to clear the LEDs on exit.

## Troubleshooting

- **No MIDI ports:** Run `--list-midi`. A MIDI Service being installed does
  not guarantee a default loopback endpoint is available to legacy WinMM apps.
- **No notes lighting:** Check Synthesia *MIDI output*, the receiving port
  paired with it, and *Finger-based channel* mode.
- **Screen test fails:** Confirm NI services are running, the S61 MK2 is not
  owned by another program, and check the helper's stderr output. Do **not**
  use Zadig to replace Native Instruments drivers.
- **Captured picture is covered or black:** This first version uses visible
  desktop capture (`mss`), not Windows Graphics Capture; leave Synthesia
  visible. A future WGC implementation can capture occluded windows.
- **Controls:** The helper outputs button/encoder events for diagnostics; the
  Synthesia shortcut mapping is deferred pending actual S61 MK2 testing.

## Testing

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions builds a Windows helper and uploads a combined artifact; this
validates compilation and pure-Python tests, **not physical keyboard operation**.

## Credits and licensing

- [SynthesiaKontrol](https://github.com/ojacques/SynthesiaKontrol) (MIT):
  published the Mk2 palette values, note ranges, and finger-channel semantics.
- [Encdr](https://github.com/RufusIbiza/Encdr) (GPL-3.0-or-later):
  underlying dual-display/LED/button hardware library.

Our source is licensed under **GPL-3.0-or-later** for compatibility with Encdr;
third-party dependencies retain their own licenses. No Encdr source code is
vendored here.
