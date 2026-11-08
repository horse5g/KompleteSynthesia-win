import unittest

from kompletesynthesia.capture import SCREEN_WIDTH, SCREEN_HEIGHT, fit_image

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "Pillow not installed")
class CaptureLayoutTests(unittest.TestCase):
    def test_all_modes(self):
        source = Image.new("RGB", (1280, 720), "white")
        for mode in ("fit", "fill", "stretch"):
            with self.subTest(mode=mode):
                self.assertEqual(fit_image(source, mode).size, (SCREEN_WIDTH, SCREEN_HEIGHT))

    def test_unknown_mode(self):
        with self.assertRaises(ValueError):
            fit_image(Image.new("RGB", (200, 100)), "unknown")


if __name__ == "__main__":
    unittest.main()
