import unittest
from kompletesynthesia.controls import Action, ControlRouter


class ControlMappingTests(unittest.TestCase):
    def test_macos_shortcuts_ported_to_encdr_names(self):
        router = ControlRouter()
        mapping = {
            "play": "space", "encoder_main_press": "enter",
            "encoder_main_left": "left", "encoder_main_right": "right",
            "encoder_main_up": "up", "encoder_main_down": "down",
            "page_left": "z", "page_right": "x",
            "top_1": "escape", "top_2": "f2",
            "top_3": "f3", "top_4": "f4",
        }
        for name, key in mapping.items():
            with self.subTest(name=name):
                self.assertEqual(
                    router.route({"kind": "button", "name": name, "pressed": True}),
                    Action("key", key),
                )
                self.assertIsNone(
                    router.route({"kind": "button", "name": name, "pressed": False})
                )

    def test_application_controls(self):
        router = ControlRouter()
        for name, action in {"top_5": "toggle_mirror", "clear": "reset",
                             "scene": "launch", "setup": "settings"}.items():
            self.assertEqual(router.route(
                {"kind": "button", "name": name, "pressed": True}), Action(action))

    def test_encoder_mapping(self):
        router = ControlRouter()
        self.assertEqual(router.route({"kind": "encoder", "name": "encoder_main",
                                       "delta": 2}), Action("wheel", -2))
        self.assertEqual(router.route({"kind": "encoder", "name": "encoder_1",
                                       "delta": -1}), Action("volume", -1))
        self.assertIsNone(router.route({"kind": "encoder", "name": "encoder_1",
                                        "delta": 0}))
