# KompleteSynthesia (macOS) to Windows 11 feature map

Original: https://github.com/tillt/KompleteSynthesia (MIT, 2023 Till Toenshoff)

| Original macOS component | Windows replacement | Status |
| --- | --- | --- |
| CoreMIDI MIDIController | Mido + python-rtmidi and Windows MIDI loopback | Implemented, hardware unverified |
| MIDI2HIDController finger channels | Python lighting.py state tracker | Ported and tested |
| Physical keyboard MIDI input | Second MIDI worker for played-note feedback | Ported, hardware unverified |
| NSUserDefaults and preferences palette | Local JSON + Tk editor | Ported, simpler UI |
| IOKit HID and raw USB | Encdr 0.9 hardware-only helper | Ported, hardware unverified |
| CGWindowListCreateImage | Python mss visible window capture | Prototype, occlusion limitation |
| Left-only original MK2 mirror | Single-screen 480x272 + standby right | Ported |
| Dual-screen span | Combined 960x272 video frame | Windows addition |
| CGEvent virtual keyboard | Win32 SendInput with Synthesia focus guard | Ported, hardware unverified |
| Play, jog, page, function buttons | Encdr descriptor names + Python router | Ported, hardware unverified |
| Scene, Clear, Setup, mirror toggle | Python reset/launch/settings/toggle | Ported |
| Status bar icon and log window | Console logging | Not yet |
| Volume OSD | --- | Not yet |
| Synthesia XML config patching | Manual setup instructions | Not yet |
| UpdateManager | GitHub Actions artifacts | No built-in updates |

## Hardware verification checklist

1. Run the screen test pattern; verify left and right LCDs separately.
2. Press Play and jogwheel and verify the debug events and shortcuts.
3. Confirm finger-based channel colors via the light-only MIDI mode.
4. Test physical-keyboard played-note overlays.
5. Run full mirror with the span and left layouts.
6. Check that stopping the app restores lights, and that Windows NI services
   do not fight for the USB interface.

CI cannot simulate the physical S61 MK2.
