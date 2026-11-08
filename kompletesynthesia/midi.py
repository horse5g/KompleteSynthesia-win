"""Mido/RtMidi ports and worker threads, including the physical S61 input."""
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
    for needle in ("Default App Loopback (B)", "Synthesia S61 Bridge",
                   "Synthesia S61", "LoopBe", "loopMIDI"):
        matches = [name for name in inputs if needle.casefold() in name.casefold()]
        if len(matches) == 1:
            return matches[0]
    raise ValueError("No supported loopback MIDI input found. Use --list-midi and --midi-port.")

def choose_keyboard_port(requested: str | None, inputs: list[str],
                         exclude: str | None = None) -> str | None:
    """Autodetect the physical keyboard (never select a MIDI loopback as an input)."""
    if requested:
        port = choose_port(requested, inputs)
        if port == exclude:
            raise ValueError("Keyboard MIDI input must differ from Synthesia loopback")
        return port
    matches = [
        name for name in inputs
        if name != exclude
        and "komplete" in name.casefold()
        and ("s61" in name.casefold() or "port 1" in name.casefold())
        and not any(term in name.casefold() for term in ("loop", "bridge"))
    ]
    return matches[0] if len(matches) == 1 else None

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
