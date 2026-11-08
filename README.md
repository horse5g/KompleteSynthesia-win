# KompleteSynthesia-win

Experimental **Windows 11 port of tillt/KompleteSynthesia** for Native Instruments Komplete Kontrol S61 MK2.

Original macOS source: https://github.com/tillt/KompleteSynthesia (MIT).
This port reimplements application behavior in Python and uses a small Rust helper
with the already-existing Encdr library (GPL-3.0-or-later) for the keyboard's
Light Guide, controls, and dual 480x272 displays.

**Hardware not yet validated.** Green CI only verifies Python tests and
compilation, not the physical USB device. Do not replace Native Instruments USB
drivers with Zadig for this project.

**Windows HID/service fallback:** The normal S61 MK2 Windows drivers do not
expose a WinUSB endpoint for nusb discovery. The Windows helper now opens the
keyboard's vendor-defined HID interface (MI_02) directly, and uses Encdr's
public Native Instruments service protocol for the two screen displays
(MI_03). No driver swap is required. The NI services must be installed and
running; see troubleshooting below.

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

## Windows S61 MK2 detection troubleshooting

If direct Light Guide testing works but the display test fails, first make sure
the compiled helper is current. After pulling the latest code, rebuild with:

    cargo build --release --manifest-path native/encdr_bridge/Cargo.toml
    python -m kompletesynthesia --test-pattern --no-midi

The development version prefers target/release/encdr_bridge.exe over an older
bin/encdr_bridge.exe if both exist. The hardware helper now reports which
interface or service it cannot open, rather than returning the generic
'nusb did not detect S61 MK2' message.

To inspect Native Instruments services (PowerShell):

    Get-Service | Where-Object { $_.Name -match 'NIHostIntegration|NIHardware' } | Format-Table Name,Status,StartType
    Test-Path 'C:\Program Files\Common Files\Native Instruments\Hardware\NIHostIntegrationAgent.exe'

The NI hardware service is required for display streaming. The Windows
process 'NisSrv.exe' is a Microsoft Defender component, **not** a Native
Instruments background service. If the NI services are missing, install or
repair Komplete Kontrol or Controller Editor through Native Access.
Do **not** replace MI_03 (Komplete Kontrol S61 MK2 BD) with WinUSB: doing so
can break Native Instruments' official display integration.

Windows MIDI note input (KOMPLETE KONTROL - 1 1) is a physical keyboard port,
not a Synthesia MIDI output loopback. To receive the falling-note light commands,
use a Windows MIDI Services loopback pair or a virtual loopback port as described
above.

## Diagnose an NI screen-service handshake refusal

If both NI services are running but the screen test reports something like
"NI service refused the connection (reply [6c, 74, 63, 65])", the HID
driver is working and the failure is at the named-pipe registration stage.
Do not install other USB drivers or reinstall NI software as a first response.

First run the read-only version probe (no keyboard needed):

    python -m kompletesynthesia --diagnose-ni

If a NI endpoint responds, close Komplete Kontrol and DAWs that may own
the controller, then run the experimental handshake comparison:

    python -m kompletesynthesia --probe-ni-handshakes

The comparison sends one short-lived registration header using Komplete
Kontrol's KKiN client identifier, and one using Encdr's Maschine NiM2
identifier, to each available bootstrap pipe. Connections are closed
immediately without controlling the displays, but successful responses
can temporarily register a client. No firmware, drivers, services or
persistent settings are changed.

Share the version and acceptance status for each pipe. Successful bootstrap
registration does not prove that LCD control or the full protocol will work.

These are diagnostics, not a fix. Encdr 0.9.0 hard-codes the Maschine
identifier. Its NI service route has been hardware verified on a Maschine
Mk3, not yet on this S61 Mk2 setup.

Reference implementations:
- https://github.com/ktemkin/DrivenByKate
- https://github.com/terminar/rebellion

## Experimental Komplete Kontrol (KKiN) NI service compatibility

The standard Encdr 0.9 NI service code registers as the Maschine NiM2 client.
A working Windows S61 MK2 reported a four-byte refusal at the first NI
bootstrap handshake, despite its HID device and both NI services working.

This branch provides a **Windows-only compatibility service client**, based on
Encdr 0.9's GPL-licensed named-pipe transport, with separate client identifiers
for Komplete Kontrol (KKiN) and Maschine (NiM2). It still uses Encdr's original
hardware screen RLE encoder and instance-setup protocol. No USB driver changes.

Default behavior: try KKiN first, then fall back to NiM2, with diagnostic
messages identifying the pipe, role, and registration stage.

    python -m kompletesynthesia --test-pattern --no-midi
    python -m kompletesynthesia --test-pattern --no-midi --ni-role kontrol
    python -m kompletesynthesia --test-pattern --no-midi --ni-role maschine

The selected role is passed as KSW_NI_ROLE to the Rust helper; no persistent
system environment variable is modified. If neither role works, run the
Python-only probes:

    python -m kompletesynthesia --diagnose-ni
    python -m kompletesynthesia --probe-ni-handshakes

To verify that you are running the updated helper, rebuild it after pulling:

    cargo build --release --manifest-path native/encdr_bridge/Cargo.toml

The helper is hardware-unverified on this S61 MK2. A successful client
registration does **not** necessarily mean NI service screen ownership and
display streaming work. If the error moves from device bootstrap to the
instance bootstrap or frame submission, please share the full stderr output.

The compatibility service transport is adapted from Encdr 0.9.0 (GPL 3.0+),
with thanks to ktemkin/DrivenByKate and terminar/rebellion for their
Komplete Kontrol client-identifier documentation.
