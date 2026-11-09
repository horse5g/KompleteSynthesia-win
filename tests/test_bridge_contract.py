"""Validate the Rust/Python ready-event contract without attached NI hardware."""
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from kompletesynthesia.bridge import EncdrBridge


class ReadyEventTests(unittest.TestCase):
    def build_reader(self, lines):
        events = []
        with patch("kompletesynthesia.bridge.find_bridge", return_value=Path("encdr_bridge.exe")):
            bridge = EncdrBridge(
                "encdr_bridge.exe", on_event=events.append,
                hid_only=True, allow_no_screens=True,
            )
        bridge.process = SimpleNamespace(
            stdout=BytesIO(lines.encode("utf-8")),
            poll=lambda: 0,
        )
        bridge._events()
        return bridge, events

    def test_hid_only_ready_and_warning(self):
        bridge, events = self.build_reader(
            '{"kind":"warning","message":"No NI LCD"}\n'
            '{"kind":"ready","device":"S61 MK2","screens":false,"backend":"hid-only"}\n'
        )
        self.assertTrue(bridge.ready.is_set())
        self.assertIsNone(bridge.startup_error)
        self.assertIs(bridge.screens, False)
        self.assertEqual([event["kind"] for event in events], ["warning", "ready"])

    def test_legacy_ready_defaults_to_screens(self):
        bridge, _ = self.build_reader('{"kind":"ready","device":"S61 MK2"}\n')
        self.assertIs(bridge.screens, True)

    def test_error_before_ready(self):
        bridge, _ = self.build_reader('{"kind":"error","message":"NI refused"}\n')
        self.assertTrue(bridge.ready.is_set())
        self.assertEqual(bridge.startup_error, "NI refused")
