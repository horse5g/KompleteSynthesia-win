import unittest
from kompletesynthesia.midi import choose_keyboard_port


class KeyboardMidiPortTests(unittest.TestCase):
    def test_autoselect_s61(self):
        ports = ["Default App Loopback (B) 0", "Komplete Kontrol S61 MK2 Port 1 1"]
        self.assertEqual(choose_keyboard_port(None, ports, ports[0]), ports[1])

    def test_ambiguous_requires_explicit(self):
        ports = ["Komplete Kontrol S61 MK2 Port 1", "Komplete Kontrol S61 MK2 Port 2"]
        self.assertIsNone(choose_keyboard_port(None, ports))

    def test_different_ports_required(self):
        with self.assertRaises(ValueError):
            choose_keyboard_port("Loopback", ["Loopback"], "Loopback")
