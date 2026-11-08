"""Windows 11 command-line app: MIDI light guide and optional screen mirror."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time

from .capture import diagnostic_pattern, find_window, grab_frame
from .lighting import LightGuide
from .midi import available_inputs, choose_port, read_midi

LOG = logging.getLogger("kompletesynthesia")


def parser():
    p = argparse.ArgumentParser(description="Synthesia -> Komplete Kontrol S61 MK2 bridge (Windows 11)")
    p.add_argument("--list-midi", action="store_true", help="List input MIDI devices, then exit")
    p.add_argument("--midi-port", help="Input MIDI port name or a unique part of it")
    p.add_argument("--no-midi", action="store_true", help="Disable MIDI, for screen hardware testing")
    p.add_argument("--light-only", action="store_true", help="Use Python hidapi directly; no screens or native helper")
    p.add_argument("--test-pattern", action="store_true", help="Display a left/right test pattern instead of capturing Synthesia")
    p.add_argument("--window-title", default="Synthesia", help="Window title substring")
    p.add_argument("--capture-mode", choices=("fit", "fill", "stretch"), default="fit")
    p.add_argument("--fps", type=int, default=12, help="Target capture frame rate (1-30)")
    p.add_argument("--bridge", help="Path to encdr_bridge.exe (optional)")
    return p


def run(argv=None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.list_midi:
        for name in available_inputs():
            print(name)
        return 0
    if os.name != "nt":
        LOG.error("Hardware bridge targets Windows 11; use Windows for connected testing")
        return 2
    if not 1 <= args.fps <= 30:
        LOG.error("--fps must be 1 to 30")
        return 2
    if args.light_only and args.test_pattern:
        LOG.error("--test-pattern requires the Encdr screen bridge, not --light-only")
        return 2

    midi_port = None
    if not args.no_midi:
        try:
            midi_port = choose_port(args.midi_port, available_inputs())
        except ValueError as exc:
            LOG.error("%s", exc)
            return 2
        LOG.info("Receiving Synthesia MIDI from: %s", midi_port)

    from contextlib import ExitStack

    stop = threading.Event()
    light_guide = LightGuide()
    light_lock = threading.Lock()
    failed: list[Exception] = []

    def on_error(exc):
        failed.append(exc)
        LOG.error("MIDI error: %s", exc)

    def on_hardware_event(event):
        kind = event.get("kind")
        if kind == "ready":
            LOG.info("Encdr connected to %s", event.get("device"))
        elif kind == "error":
            LOG.error("Encdr: %s", event.get("message"))
            failed.append(RuntimeError(str(event.get("message"))))
            stop.set()
        elif kind == "button" and event.get("pressed"):
            LOG.info("Keyboard button: %s", event.get("name"))
        elif kind == "encoder":
            LOG.debug("Encoder %s: %s", event.get("name"), event.get("delta"))

    try:
        with ExitStack() as stack:
            if args.light_only:
                from .hardware import DirectLightGuide

                hardware = stack.enter_context(DirectLightGuide())
            else:
                from .bridge import EncdrBridge

                hardware = stack.enter_context(EncdrBridge(args.bridge, on_event=on_hardware_event))

            def on_message(message):
                with light_lock:
                    if light_guide.apply(message):
                        hardware.set_lights(light_guide.colors())

            if midi_port:
                t = threading.Thread(target=read_midi, args=(midi_port, on_message, stop, on_error), daemon=True)
                t.start()
            if args.light_only:
                LOG.info("Light-only mode. Press Ctrl+C to stop.")
                while not stop.wait(0.2):
                    pass
            elif args.test_pattern:
                hardware.set_lights(bytes([0x2D if n < 30 else 0x1D for n in range(61)]))
                hardware.send_frame(diagnostic_pattern().convert("RGBA").tobytes())
                LOG.info("Test pattern sent. Press Ctrl+C to stop.")
                while not stop.wait(0.2):
                    pass
            else:
                from mss import MSS

                hwnd = None
                last_notice = 0.0
                with MSS() as sct:
                    while not stop.is_set():
                        started = time.monotonic()
                        if hwnd is None:
                            hwnd = find_window(args.window_title)
                        if hwnd is None:
                            if started - last_notice >= 5:
                                LOG.warning("Waiting for visible '%s' window", args.window_title)
                                last_notice = started
                            stop.wait(0.5)
                            continue
                        try:
                            frame = grab_frame(sct, hwnd, args.capture_mode)
                        except (RuntimeError, OSError) as exc:
                            LOG.warning("Capture unavailable: %s", exc)
                            hwnd = None
                            stop.wait(0.3)
                            continue
                        hardware.send_frame(frame.convert("RGBA").tobytes())
                        stop.wait(max(0.0, 1 / args.fps - (time.monotonic() - started)))
    except KeyboardInterrupt:
        LOG.info("Stopping")
    except (OSError, FileNotFoundError, RuntimeError) as exc:
        LOG.error("%s", exc)
        return 1
    finally:
        stop.set()
    return 1 if failed else 0


def main():
    sys.exit(run())
