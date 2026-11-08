# KompleteSynthesia-win

Experimental **Windows 11 port of tillt/KompleteSynthesia** for Native Instruments Komplete Kontrol S61 MK2.

Original macOS source: https://github.com/tillt/KompleteSynthesia (MIT).
This port reimplements application behavior in Python and uses a small Rust helper
with the already-existing Encdr library (GPL-3.0-or-later) for the keyboard's
Light Guide, controls, and dual 480x272 displays.

**Hardware not yet validated.** Green CI only verifies Python tests and
compilation, not the physical USB device. Do not replace Native Instruments USB
drivers with Zadig for this project.

## Ported behavior

- Synthesia finger-channel MIDI lights, left/right hands and thumbs
- Played-note highlighting from the keyboard's separate MIDI Port 1 input
- Eight saved Light Guide palette colors (including played-note colors)
- Play, jogwheel, Page, top 1–5, Clear, Scene, Setup and volume encoder shortcuts
- Two screen layouts: span (960x272) and original-style left-only (480x272)
- Persistent JSON preferences and a Windows Tk preferences window
- Native SendInput shortcuts, guarded so typing cannot target unrelated apps
- MIDI Services loopback compatibility, without requiring LoopBe1 if the
  Windows loopback endpoints are available to Synthesia and RtMidi
- Screen test pattern and light-only hardware diagnostic mode

## Requirements

- Windows 11 x64 with Python 3.11 or later and Synthesia
- Native Instruments drivers/services as required by Encdr's Windows display transport
- A Windows MIDI Services loopback pair, or another compatible virtual MIDI port
- The encdr_bridge.exe prebuilt Windows build artifact, or Rust/MSVC to build it

This app does not create a virtual MIDI port by itself.

## Installation

Clone https://github.com/horse5g/KompleteSynthesia-win and run in PowerShell:

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt

Get the KompleteSynthesia-win-W11 artifact from
https://github.com/horse5g/KompleteSynthesia-win/actions
and put its bin/encdr_bridge.exe into this repository's bin directory.

Or build the helper locally:

    cargo build --release --manifest-path native/encdr_bridge/Cargo.toml

## MIDI setup (no LoopBe1 if Windows MIDI Services loopback works)

In Synthesia -> Settings -> Music Devices, select Default App Loopback (A)
as a MIDI output and set Key Lights to Finger-based channel. The app listens
on Default App Loopback (B). This is only available if both ends are exposed
on your installation to Synthesia and mido/python-rtmidi. Otherwise configure
another virtual loopback port and pass its input name via --midi-port.

The physical keyboard's MIDI Port 1 input is separate and optional.
Use --list-midi to see device names and --keyboard-midi-port to select one.

## Run

    python -m kompletesynthesia --list-midi
    python -m kompletesynthesia --light-only --midi-port "Default App Loopback (B)"
    python -m kompletesynthesia --test-pattern --no-midi
    python -m kompletesynthesia --midi-port "Default App Loopback (B)"
    python -m kompletesynthesia --display-layout left
    python -m kompletesynthesia --settings
    python -m kompletesynthesia --init-config
    python -m unittest discover -s tests -v

Use --help for other options. Ctrl+C exits and attempts to turn off the LEDs.

## Ported controls

| Hardware control | Windows action |
| --- | --- |
| Play | Space |
| Main jog press and directions | Enter / arrow keys |
| Main jog rotation | Mouse wheel |
| Page left / right | Z / X |
| Top buttons 1, 2, 3, 4 | Escape / F2 / F3 / F4 |
| Top button 5 | Toggle screen mirror |
| Clear | Clear notes and LEDs |
| Scene | Launch Synthesia if detected |
| Setup | Launch the settings editor |
| Encoder 1 | Windows master volume up/down |

--no-controls disables these shortcuts.

## Preferences

Run python -m kompletesynthesia --settings to edit the colors, mirroring
defaults and shortcuts. Settings live in the Windows LOCALAPPDATA directory,
under KompleteSynthesia-win/settings.json. Changes require restarting the
bridge. The physical Setup button opens the same editor.

## Known limitations

- Current screen capture uses mss on the visible desktop. A window obscuring
  Synthesia will also be captured. Minimized-window capture is unsupported.
  A WinRT Windows Graphics Capture backend is planned.
- The original macOS menu-bar status icon, update checks, automatic Synthesia
  XML configuration patch, and volume OSD are not yet ported.
- The settings editor is simpler than the original Cocoa palette picker.
- Exact physical device MIDI port names, Encdr display transport, and control
  mapping still require hardware testing.
- Light-only mode and Encdr bridge should not run simultaneously.

See PORTING.md for full feature-by-feature progress and
THIRD_PARTY_NOTICES.md for MIT attribution and license details.
