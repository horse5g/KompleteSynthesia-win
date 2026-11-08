"""Synthesia MIDI finger channels and played-note feedback -> MK2 palette bytes.

Adapts the behavior of tillt/KompleteSynthesia's MIDI2HIDController (MIT).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from .preferences import ColorPalette

KEY_COUNT = 61
FIRST_NOTE = 36
BLUE = 0x2D
BLUE_THUMB = 0x2F
GREEN = 0x1D
GREEN_THUMB = 0x1F

def channel_role(channel: int) -> str:
    if channel == 1:
        return "left_thumb"
    if 2 <= channel <= 5 or channel == 11:
        return "left"
    if channel == 6:
        return "right_thumb"
    return "right"

def palette_for_channel(channel: int) -> int:
    return getattr(ColorPalette(), channel_role(channel))

@dataclass
class LightGuide:
    first_note: int = FIRST_NOTE
    key_count: int = KEY_COUNT
    palette: ColorPalette = field(default_factory=ColorPalette)
    # A key may be active in multiple Synthesia channels at once.
    active: dict[tuple[int, int], str] = field(default_factory=dict)
    # Notes sent by the physical S61 MIDI input rather than Synthesia loopback.
    pressed: set[int] = field(default_factory=set)

    def clear(self, source: str = "all") -> bool:
        before = self.colors()
        if source in ("synthesia", "all"):
            self.active.clear()
        if source in ("keyboard", "all"):
            self.pressed.clear()
        return self.colors() != before

    def apply(self, message: object, source: str = "synthesia") -> bool:
        """Process a mido message; return whether the visible LED frame changed."""
        if source not in ("synthesia", "keyboard"):
            raise ValueError(f"Unknown MIDI source {source}")
        kind = getattr(message, "type", "")
        if kind == "control_change":
            control = getattr(message, "control", -1)
            if control in (120, 121, 123):
                return self.clear(source)
            if source == "synthesia" and control == 16 and getattr(message, "channel", -1) == 0:
                return self.clear("synthesia")
            return False
        if kind not in ("note_on", "note_off"):
            return False
        note = int(message.note)
        if not self.first_note <= note < self.first_note + self.key_count:
            return False
        before = self.colors()[note - self.first_note]
        on = kind == "note_on" and getattr(message, "velocity", 0) != 0
        if source == "keyboard":
            if on:
                self.pressed.add(note)
            else:
                self.pressed.discard(note)
        else:
            token = (note, int(getattr(message, "channel", 0)))
            if on:
                self.active[token] = channel_role(token[1])
            else:
                self.active.pop(token, None)
        return self.colors()[note - self.first_note] != before

    def colors(self) -> bytes:
        frame = bytearray([self.palette.unpressed] * self.key_count)
        for (note, _), role in self.active.items():
            frame[note - self.first_note] = getattr(self.palette, role)
        for note in self.pressed:
            role = None
            for (candidate, _), value in self.active.items():
                if candidate == note:
                    role = value
            if role and role.startswith("left"):
                color = self.palette.left_pressed
            elif role and role.startswith("right"):
                color = self.palette.right_pressed
            else:
                color = self.palette.pressed
            frame[note - self.first_note] = color
        return bytes(frame)
