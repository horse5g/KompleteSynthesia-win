import unittest
from types import SimpleNamespace

from kompletesynthesia.lighting import LightGuide, BLUE, BLUE_THUMB, GREEN, GREEN_THUMB
from kompletesynthesia.midi import choose_port


def note(kind, pitch, channel=0, velocity=64):
    return SimpleNamespace(type=kind, note=pitch, channel=channel, velocity=velocity)


class LightGuideTests(unittest.TestCase):
    def test_61_key_boundaries(self):
        guide = LightGuide()
        self.assertFalse(guide.apply(note("note_on", 35)))
        self.assertTrue(guide.apply(note("note_on", 36, channel=2)))
        self.assertTrue(guide.apply(note("note_on", 96, channel=6)))
        self.assertFalse(guide.apply(note("note_on", 97)))
        self.assertEqual(guide.colors()[0], BLUE)
        self.assertEqual(guide.colors()[-1], GREEN_THUMB)
        self.assertEqual(len(guide.colors()), 61)

    def test_hands_and_thumb(self):
        guide = LightGuide()
        guide.apply(note("note_on", 40, channel=1))
        guide.apply(note("note_on", 41, channel=6))
        guide.apply(note("note_on", 42, channel=0))
        self.assertEqual(guide.colors()[4:7], bytes((BLUE_THUMB, GREEN_THUMB, GREEN)))

    def test_note_on_velocity_zero_is_off(self):
        guide = LightGuide()
        guide.apply(note("note_on", 60))
        self.assertTrue(guide.apply(note("note_on", 60, velocity=0)))
        self.assertEqual(guide.colors()[24], 0)

    def test_overlapping_hands(self):
        guide = LightGuide()
        guide.apply(note("note_on", 60, channel=2))
        guide.apply(note("note_on", 60, channel=8))
        guide.apply(note("note_off", 60, channel=8))
        self.assertEqual(guide.colors()[24], BLUE)

    def test_cc16_clears(self):
        guide = LightGuide()
        guide.apply(note("note_on", 60))
        self.assertTrue(guide.apply(SimpleNamespace(type="control_change", control=16, channel=0, value=1)))
        self.assertEqual(guide.colors(), bytes(61))

    def test_all_notes_off(self):
        guide = LightGuide()
        guide.apply(note("note_on", 60))
        self.assertTrue(guide.apply(SimpleNamespace(type="control_change", control=123, channel=8)))
        self.assertEqual(guide.colors(), bytes(61))

    def test_port_selection(self):
        names = ["Default App Loopback (B) 1", "Komplete Kontrol S61"]
        self.assertEqual(choose_port(None, names), names[0])
        self.assertEqual(choose_port("Loopback", names), names[0])
        with self.assertRaises(ValueError):
            choose_port("no-such-port", names)


if __name__ == "__main__":
    unittest.main()
