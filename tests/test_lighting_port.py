from types import SimpleNamespace
import unittest

from kompletesynthesia.lighting import LightGuide
from kompletesynthesia.preferences import ColorPalette


def event(kind, note=60, channel=0, velocity=64, control=-1):
    return SimpleNamespace(type=kind, note=note, channel=channel, velocity=velocity, control=control)


class PlayedNoteTests(unittest.TestCase):
    def test_pressed_colors_overlay(self):
        palette = ColorPalette(unpressed=0x44, pressed=0x47, left_pressed=0x2F, right_pressed=0x1F)
        guide = LightGuide(palette=palette)
        self.assertEqual(guide.colors()[24], 0x44)
        guide.apply(event("note_on", channel=2))
        guide.apply(event("note_on"), "keyboard")
        self.assertEqual(guide.colors()[24], 0x2F)
        guide.apply(event("note_off"), "keyboard")
        self.assertEqual(guide.colors()[24], palette.left)
        guide.apply(event("note_off", channel=2))
        self.assertEqual(guide.colors()[24], 0x44)

    def test_keyboard_only_and_cc16(self):
        guide = LightGuide()
        guide.apply(event("note_on"), "keyboard")
        guide.apply(event("note_on", channel=8))
        guide.apply(event("control_change", channel=0, control=16))
        self.assertEqual(guide.colors()[24], guide.palette.pressed)
        guide.apply(event("control_change", channel=1, control=123), "keyboard")
        self.assertEqual(guide.colors()[24], guide.palette.unpressed)

    def test_overlapping_channels_keep_hand(self):
        guide = LightGuide()
        guide.apply(event("note_on", channel=2))
        guide.apply(event("note_on", channel=8))
        guide.apply(event("note_off", channel=8))
        self.assertEqual(guide.colors()[24], guide.palette.left)
