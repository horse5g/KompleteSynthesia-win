"""MIDI port discovery and MIDI event worker using Mido/RtMidi."""

from __future__ import annotations

import threading


def available_inputs() -> list[str]:
    import mido

    return mido.get_input_names()


def choose_port(requested: str | None, inputs: list[str]) -> str:
    if requested:
        matches = [name for name in inputs if requested.casefold() in name.casefold()]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ValueError(f"No MIDI input matches {requested!r}. Available: {inputs}")
        raise ValueError(f"Ambiguous MIDI input {requested!r}: {matches}")
    for needle in ("Default App Loopback (B)", "Synthesia S61 Bridge", "Synthesia S61", "LoopBe", "loopMIDI"):
        matches = [name for name in inputs if needle.casefold() in name.casefold()]
        if len(matches) == 1:
            return matches[0]
    raise ValueError("No supported loopback MIDI input found. Use --list-midi and --midi-port.")


def read_midi(port_name: str, on_message, stop: threading.Event, on_error):
    import mido

    try:
        with mido.open_input(port_name) as port:
            while not stop.wait(0.005):
                for message in port.iter_pending():
                    on_message(message)
    except Exception as exc:
        on_error(exc)
        stop.set()
