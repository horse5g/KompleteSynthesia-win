import tempfile
import unittest
from pathlib import Path
from kompletesynthesia.app import parser, run

class AppSmokeTests(unittest.TestCase):
    def test_new_cli_arguments(self):
        args = parser().parse_args(["--display-layout", "left", "--no-controls", "--fps", "15"])
        self.assertEqual(args.display_layout, "left")
        self.assertTrue(args.no_controls)
        self.assertEqual(args.fps, 15)
        self.assertEqual(args.ni_role, "auto")
        self.assertEqual(parser().parse_args(["--ni-role", "kontrol"]).ni_role, "kontrol")

    def test_initialize_settings_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "settings.json"
            self.assertEqual(run(["--config", str(config), "--init-config"]), 0)
            self.assertTrue(config.exists())
            self.assertIn("palette", config.read_text(encoding="utf-8"))
