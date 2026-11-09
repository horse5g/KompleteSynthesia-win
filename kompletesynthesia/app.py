"""Windows 11 command-line bridge, porting macOS KompleteSynthesia features to Python."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from .capture import diagnostic_pattern, find_window, grab_frame, idle_screen
from .controls import ControlRouter, send_windows_action
from .lighting import LightGuide
from .midi import available_inputs, choose_port, choose_keyboard_port, read_midi
from .preferences import config_path, load_settings, save_settings

LOG = logging.getLogger("kompletesynthesia")


def parser():
    p = argparse.ArgumentParser(
        description="KompleteSynthesia for Windows 11 — Native Instruments S61 MK2")
    p.add_argument("--list-midi", action="store_true", help="List MIDI input ports")
    p.add_argument("--diagnose-ni", action="store_true",
                   help="Probe NI hardware-service version endpoints without connecting")
    p.add_argument("--probe-ni-handshakes", action="store_true",
                   help="Compare short-lived Komplete Kontrol and Maschine NI registration handshakes")
    p.add_argument("--midi-port", help="Synthesia output loopback MIDI input")
    p.add_argument("--keyboard-midi-port", help="Physical S61 MK2 Port 1 MIDI input")
    p.add_argument("--no-midi", action="store_true", help="Disable both MIDI receivers")
    p.add_argument("--no-keyboard-midi", action="store_true", help="Disable the physical keyboard receiver")
    p.add_argument("--no-controls", action="store_true", help="Disable hardware shortcut forwarding")
    p.add_argument("--light-only", action="store_true", help="Direct HID LEDs only, no screens")
    p.add_argument("--hid-only", action="store_true",
                   help="Use Rust HID backend for lights and physical buttons without NI screens")
    p.add_argument("--allow-no-screens", action="store_true",
                   help="Attempt NI displays, but continue HID controls and lights if unavailable")
    p.add_argument("--test-pattern", action="store_true", help="Send a fixed left/right screen test")
    p.add_argument("--window-title", default="Synthesia", help="Synthesia window title substring")
    p.add_argument("--capture-mode", choices=("fit", "fill", "stretch"))
    p.add_argument("--display-layout", choices=("span", "left"),
                   help="Mirror across both displays or original left-only view")
    p.add_argument("--fps", type=int, help="Frames per second, 1-30")
    p.add_argument("--bridge", help="Path to encdr_bridge.exe")
    p.add_argument("--ni-role", choices=("auto", "kontrol", "maschine"), default="auto",
                   help="NI service client-kind preference (default: auto, Komplete first)")
    p.add_argument("--config", type=Path, help="Override the settings.json location")
    p.add_argument("--init-config", action="store_true", help="Write default config and exit")
    p.add_argument("--settings", action="store_true", help="Open preferences window and exit")
    return p


def launch_synthesia() -> bool:
    """Launch a commonly installed Synthesia.exe without using a shell."""
    paths = [shutil.which("Synthesia.exe")]
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(env)
        if root:
            paths.extend([str(Path(root) / "Synthesia" / "Synthesia.exe"),
                          str(Path(root) / "Programs" / "Synthesia" / "Synthesia.exe")])
    for path in paths:
        if path and Path(path).is_file():
            subprocess.Popen([path])
            return True
    return False


def run(argv=None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    path = args.config or config_path()

    try:
        settings = load_settings(path)
        if args.init_config:
            save_settings(settings, path)
            print(f"Settings written: {path}")
            return 0
        if args.settings:
            from .preferences_ui import show_preferences
            show_preferences(path)
            return 0
    except (OSError, ValueError) as exc:
        LOG.error("%s", exc)
        return 2

    if args.diagnose_ni or args.probe_ni_handshakes:
        from .ni_probe import diagnostics
        for line in diagnostics(probe_connections=args.probe_ni_handshakes):
            print(line)
        return 0
    if args.list_midi:
        for name in available_inputs():
            print(name)
        return 0
    if os.name != "nt":
        LOG.error("Physical hardware bridge targets Windows 11")
        return 2
    if args.light_only and args.test_pattern:
        LOG.error("--test-pattern requires the Encdr helper")
        return 2
    if args.light_only and args.hid_only:
        LOG.error("--light-only (Python direct HID) and --hid-only (Rust HID/controls) conflict")
        return 2
    if args.hid_only and args.test_pattern:
        LOG.error("--test-pattern requires screens; remove --hid-only")
        return 2

    fps = args.fps if args.fps is not None else settings.fps
    if not 1 <= fps <= 30:
        LOG.error("--fps must be between 1 and 30")
        return 2
    mode = args.capture_mode or settings.capture_mode
    layout = args.display_layout or settings.display_layout
    control_enabled = settings.controls_enabled and not args.no_controls and not args.light_only
    mirror_active = threading.Event()
    if settings.mirror_enabled:
        mirror_active.set()

    inputs = []
    if not args.no_midi:
        try:
            inputs = available_inputs()
            light_port = choose_port(args.midi_port or settings.midi_port, inputs)
            keyboard_port = None if args.no_keyboard_midi else choose_keyboard_port(
                args.keyboard_midi_port or settings.keyboard_midi_port,
                inputs, exclude=light_port,
            )
        except ValueError as exc:
            LOG.error("%s", exc)
            return 2
        LOG.info("Synthesia lighting MIDI: %s", light_port)
        if "komplete kontrol" in light_port.casefold():
            LOG.warning(
                "%s appears to be a physical S61 keyboard MIDI input, "
                "not a virtual MIDI loopback for Synthesia output. "
                "Use a MIDI Services loopback or loopMIDI for falling-note lights.",
                light_port,
            )
        if keyboard_port:
            LOG.info("Physical keyboard MIDI: %s", keyboard_port)
        elif not args.no_keyboard_midi:
            LOG.info("Physical keyboard MIDI port not identified; "
                     "use --keyboard-midi-port to enable pressed-note highlighting.")
    else:
        light_port, keyboard_port = None, None

    stop = threading.Event()
    light_guide = LightGuide(palette=settings.palette)
    light_lock = threading.Lock()
    failures: list[Exception] = []
    router = ControlRouter()
    hardware = None

    def on_error(exc):
        failures.append(exc)
        LOG.error("MIDI error: %s", exc)
        stop.set()

    def on_message(message, source="synthesia"):
        with light_lock:
            if light_guide.apply(message, source=source):
                hardware.set_lights(light_guide.colors())

    def on_hardware_event(event):
        kind = event.get("kind")
        if kind == "ready":
            LOG.info("Hardware connected to %s (backend=%s, screens=%s)",
                     event.get("device"), event.get("backend", "unknown"),
                     event.get("screens", "unknown"))
            return
        if kind == "warning":
            LOG.warning("Hardware: %s", event.get("message", "Nonfatal warning"))
            return
        if kind == "error":
            error = RuntimeError(str(event.get("message")))
            failures.append(error)
            LOG.error("Encdr: %s", error)
            stop.set()
            return
        if not control_enabled or not hardware:
            return
        action = router.route(event)
        if action is None:
            return
        LOG.debug("S61 event %s -> %s", event, action)
        try:
            if action.kind == "toggle_mirror":
                if mirror_active.is_set():
                    mirror_active.clear()
                    hardware.send_frame(idle_screen().convert("RGBA").tobytes())
                    LOG.info("Synthesia screen mirroring disabled")
                else:
                    mirror_active.set()
                    LOG.info("Synthesia screen mirroring enabled")
            elif action.kind == "reset":
                with light_lock:
                    light_guide.clear()
                    hardware.set_lights(light_guide.colors())
                LOG.info("Light Guide reset")
            elif action.kind == "settings":
                subprocess.Popen([sys.executable, "-m", "kompletesynthesia",
                                  "--settings", "--config", str(path)])
            elif action.kind == "launch":
                if find_window(args.window_title) is None and not launch_synthesia():
                    LOG.warning("Synthesia.exe wasn't found in standard install locations")
            else:
                hwnd = find_window(args.window_title) if action.kind != "volume" else None
                if not send_windows_action(action, hwnd, settings.focus_synthesia):
                    LOG.warning("Cannot forward %s: Synthesia not focused/available", action)
        except (OSError, RuntimeError, ValueError) as exc:
            LOG.warning("Hardware control %s failed: %s", action, exc)

    try:
        with ExitStack() as stack:
            if args.light_only:
                from .hardware import DirectLightGuide
                hardware = stack.enter_context(DirectLightGuide())
            else:
                from .bridge import EncdrBridge
                hardware = stack.enter_context(
                    EncdrBridge(
                        args.bridge, on_event=on_hardware_event, ni_role=args.ni_role,
                        hid_only=args.hid_only, allow_no_screens=args.allow_no_screens
                    )
                )

            hardware.set_lights(light_guide.colors())

            if light_port:
                threading.Thread(
                    target=read_midi, args=(light_port, on_message, stop, on_error),
                    daemon=True, name="synthesia-midi",
                ).start()
            if keyboard_port:
                threading.Thread(
                    target=read_midi,
                    args=(keyboard_port, lambda m: on_message(m, "keyboard"), stop, on_error),
                    daemon=True, name="physical-keyboard-midi",
                ).start()

            if args.light_only:
                LOG.info("Light-only mode; Ctrl+C to exit")
                while not stop.wait(0.2):
                    pass
            elif args.test_pattern:
                if not hardware.screens:
                    raise RuntimeError("Screen test requested but NI LCD service is unavailable")
                hardware.set_lights(bytes([0x2D if i < 30 else 0x1D for i in range(61)]))
                hardware.send_frame(diagnostic_pattern().convert("RGBA").tobytes())
                LOG.info("Screen test pattern sent; Ctrl+C to exit")
                while not stop.wait(0.2):
                    pass
            elif args.hid_only or hardware.screens is False:
                LOG.info("HID-only running: Light Guide and S61 buttons enabled; LCD mirroring disabled. Ctrl+C to exit")
                while not stop.wait(0.2):
                    pass
            else:
                from mss import MSS
                LOG.info("Active mirror layout: %s / %s, %d FPS", layout, mode, fps)
                if not mirror_active.is_set():
                    hardware.send_frame(idle_screen().convert("RGBA").tobytes())
                hwnd = None
                last_notice = 0.0
                with MSS() as sct:
                    while not stop.is_set():
                        started = time.monotonic()
                        if not mirror_active.is_set():
                            stop.wait(0.1)
                            continue
                        if hwnd is None:
                            hwnd = find_window(args.window_title)
                        if hwnd is None:
                            if started - last_notice >= 5:
                                LOG.warning("Waiting for visible '%s' window", args.window_title)
                                last_notice = started
                            stop.wait(0.5)
                            continue
                        try:
                            frame = grab_frame(sct, hwnd, mode, layout)
                        except (RuntimeError, OSError) as exc:
                            LOG.warning("Screen capture unavailable: %s", exc)
                            hwnd = None
                            stop.wait(0.3)
                            continue
                        # Main thread sends video frames. The helper serializes USB I/O.
                        hardware.send_frame(frame.convert("RGBA").tobytes())
                        stop.wait(max(0.0, 1 / fps - (time.monotonic() - started)))
    except KeyboardInterrupt:
        LOG.info("Stopping")
    except (OSError, FileNotFoundError, RuntimeError) as exc:
        LOG.error("%s", exc)
        return 1
    finally:
        stop.set()
    return 1 if failures else 0


def main():
    sys.exit(run())
