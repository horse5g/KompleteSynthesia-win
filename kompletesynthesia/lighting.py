"""Synthesia finger-channel MIDI messages -> S61 Mk2 light-guide palette bytes.

The S61 Mk2 covers MIDI notes 36 through 96.  The hardware palette bytes and
Synthesia channel mapping were documented by the SynthesiaKontrol project.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KEY_COUNT = 61
FIRST_NOTE = 36
BLUE = 0x2D
BLUE_THUMB = 0x2F
GREEN = 0x1D
GREEN_THUMB = 0x1F


def palette_for_channel(channel: int) -> int:
    """Synthesia's 'Finger-based channel' mode, channels numbered from zero."""
    if channel == 1:
        return BLUE_THUMB
    if 2 <= channel <= 5 or channel == 11:
        return BLUE
    if channel == 6:
        return GREEN_THUMB
    return GREEN


@dataclass
class LightGuide:
    first_note: int = FIRST_NOTE
    key_count: int = KEY_COUNT
    # Each note may be sounding from multiple hands/channels concurrently.
    active: dict[tuple[int, int], int] = field(default_factory=dict)

    def clear(self) -> bool:
        changed = bool(self.active)
        self.active.clear()
        return changed

    def apply(self, message: object) -> bool:
        """Apply a mido-style message. Returns True if the displayed colors changed."""
        kind = getattr(message, "type", "")
        if kind == "control_change":
            if getattr(message, "control", -1) in (120, 121, 123):
                return self.clear()
            # Synthesia uses channel-zero CC16 as a mode/hand-state indicator.
            if getattr(message, "control", -1) == 16 and getattr(message, "channel", -1) == 0:
                return self.clear()
            return False
        if kind not in ("note_on", "note_off"):
            return False
        note = int(message.note)
        if not self.first_note <= note < self.first_note + self.key_count:
            return False
        channel = int(getattr(message, "channel", 0))
        token = (note, channel)
        before = self.colors()[note - self.first_note]
        if kind == "note_off" or getattr(message, "velocity", 0) == 0:
            self.active.pop(token, None)
        else:
            self.active[token] = palette_for_channel(channel)
        return self.colors()[note - self.first_note] != before

    def colors(self) -> bytes:
        frame = bytearray(self.key_count)
        for (note, _), color in self.active.items():
            frame[note - self.first_note] = color
        return bytes(frame)
