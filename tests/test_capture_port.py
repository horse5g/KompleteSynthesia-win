import unittest
from kompletesynthesia.capture import fit_image, idle_screen, SCREEN_WIDTH, SCREEN_HEIGHT

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "Pillow not installed")
class ScreenLayoutTests(unittest.TestCase):
    def test_original_single_screen_mode(self):
        input_image = Image.new("RGB", (640, 480), "red")
        result = fit_image(input_image, "fill", "left")
        self.assertEqual(result.size, (SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual(result.getpixel((100, 140)), (255, 0, 0))
        self.assertNotEqual(result.getpixel((700, 140)), (255, 0, 0))

    def test_span_layout(self):
        result = fit_image(Image.new("RGB", (640, 480), "red"), "stretch")
        self.assertEqual(result.getpixel((700, 140)), (255, 0, 0))

    def test_invalid_layout(self):
        with self.assertRaises(ValueError):
            fit_image(Image.new("RGB", (100, 100)), layout="bad")

    def test_standby_image(self):
        self.assertEqual(idle_screen().size, (960, 272))
