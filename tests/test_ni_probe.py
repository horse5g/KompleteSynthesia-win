import struct
import unittest

from kompletesynthesia.ni_probe import (
    PIPES, ROLE_KONTROL, ROLE_MASCHINE, VERSION_MESSAGE, TRUE_WORD,
    describe_reply, device_connect, diagnostics,
)


class NIHandshakeTests(unittest.TestCase):
    def test_version_packet(self):
        self.assertEqual(VERSION_MESSAGE, bytes.fromhex("56 67 53 03"))

    def test_distinct_client_identifiers(self):
        kontrol = device_connect(ROLE_KONTROL)
        maschine = device_connect(ROLE_MASCHINE)
        self.assertEqual(len(kontrol), 21)
        self.assertEqual(kontrol[16:20], b"\x01\x00\x00\x00")
        self.assertEqual(kontrol[-1], 0)
        self.assertEqual(len(device_connect(ROLE_KONTROL, terminated_serial=False)), 20)
        self.assertEqual(kontrol[:8], bytes.fromhex("00 75 44 03 20 16 00 00"))
        self.assertEqual(struct.unpack_from("<I", kontrol, 8)[0], ROLE_KONTROL)
        self.assertEqual(struct.unpack_from("<I", maschine, 8)[0], ROLE_MASCHINE)
        self.assertNotEqual(kontrol, maschine)

    def test_diagnostic_does_not_handshake_by_default(self):
        seen = []

        def exchange(name, message):
            seen.append((name, message))
            return bytes.fromhex("00 09 01 00 03 00 00 00")

        output = diagnostics(exchange=exchange)
        self.assertEqual(len(seen), len(PIPES))
        self.assertTrue(all(message == VERSION_MESSAGE for _, message in seen))
        self.assertTrue(any("--probe-ni-handshakes" in line for line in output))

    def test_connection_probe_checks_each_role_on_each_pipe(self):
        seen = []

        def exchange(name, message):
            seen.append((name, message))
            if message == VERSION_MESSAGE:
                return bytes.fromhex("00 09 01 00 03 00 00 00")
            if message == device_connect(ROLE_KONTROL):
                return TRUE_WORD + (b"\x00" * 12)
            return bytes.fromhex("6c 74 63 65")

        output = diagnostics(probe_connections=True, exchange=exchange)
        self.assertEqual(len(seen), 10)
        self.assertTrue(any("connect Komplete Kontrol (KKiN) [nul-terminated-21]: accepted" in s for s in output))
        self.assertTrue(any("connect Maschine (NiM2) [nul-terminated-21]: four-byte refusal" in s for s in output))
        self.assertEqual(seen[1][1], device_connect(ROLE_KONTROL, terminated_serial=True))
        self.assertEqual(seen[2][1], device_connect(ROLE_KONTROL, terminated_serial=False))
        self.assertEqual(seen[3][1], device_connect(ROLE_MASCHINE, terminated_serial=True))

    def test_error_continues_other_pipe(self):
        def exchange(name, message):
            if name == PIPES[0]:
                raise OSError("unavailable")
            return b"\x00"
        output = diagnostics(exchange=exchange)
        self.assertTrue(any("unavailable" in s for s in output))
        self.assertTrue(any(PIPES[1] in s for s in output))

    def test_reply_shows_only_prefix_not_port_names(self):
        data = TRUE_WORD + bytes(4) + b"SECRET_SERIAL_PRIVATE"
        output = describe_reply(data)
        self.assertIn("accepted", output)
        self.assertNotIn("SECRET", output)
