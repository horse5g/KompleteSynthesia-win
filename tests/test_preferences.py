import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from kompletesynthesia.preferences import ColorPalette, Settings, load_settings, save_settings


class SettingsTests(unittest.TestCase):
    def test_defaults_and_partial_palette(self):
        settings = Settings.from_dict({"palette": {"left": 0x35}, "fps": 18})
        self.assertEqual(settings.palette.left, 0x35)
        self.assertEqual(settings.palette.right, ColorPalette().right)
        self.assertEqual(settings.fps, 18)

    def test_reject_invalid_values(self):
        for obj in (
            {"palette": {"left": -1}}, {"palette": {"right": 256}},
            {"palette": {"left": True}}, {"fps": 0},
            {"controls_enabled": "yes"}, {"capture_mode": "broken"},
            {"display_layout": "sideways"}, ["unexpected"],
        ):
            with self.subTest(obj=obj):
                with self.assertRaises(ValueError):
                    Settings.from_dict(obj)

    def test_save_and_reload(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "prefs.json"
            settings = Settings(mirror_enabled=False, keyboard_midi_port="S61 Port 1")
            save_settings(settings, path)
            self.assertEqual(load_settings(path).to_dict(), settings.to_dict())
            self.assertIn('"mirror_enabled": false', path.read_text())
