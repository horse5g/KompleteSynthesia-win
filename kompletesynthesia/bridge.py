"""Binary IPC for the Encdr HID/service helper.

Commands: L + 61 palette bytes; F + 960x272 RGBA bytes; Q.
Responses: newline-delimited JSON on stdout; diagnostic text on stderr.

We wait for the helper to send 'ready' before returning, so a failing helper
does not produce a second, misleading '[Errno 32] Broken pipe' traceback.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import threading

FRAME_SIZE = 960 * 272 * 4


def find_bridge(explicit: str | None = None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise FileNotFoundError(f"Encdr helper not found: {path}")
        return path
    base = Path(__file__).resolve().parent.parent
    for path in (
        base / "native" / "encdr_bridge" / "target" / "release" / "encdr_bridge.exe",
        base / "bin" / "encdr_bridge.exe",
        base / "native" / "encdr_bridge" / "target" / "debug" / "encdr_bridge.exe",
    ):
        if path.is_file():
            return path
    raise FileNotFoundError("Encdr helper missing. Download the Windows artifact or compile native/encdr_bridge.")


class EncdrBridge:
    def __init__(self, binary: str | None = None, on_event=None, ni_role: str = "auto",
                 hid_only: bool = False, allow_no_screens: bool = False):
        self.binary = find_bridge(binary)
        self.hid_only = bool(hid_only)
        self.allow_no_screens = bool(allow_no_screens)
        self.screens: bool | None = None
        self.on_event = on_event or (lambda event: None)
        if ni_role not in ("auto", "kontrol", "maschine"):
            raise ValueError(f"Unknown NI client role {ni_role!r}")
        self.ni_role = ni_role
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.output_thread: threading.Thread | None = None
        self.ready = threading.Event()
        self.startup_error: str | None = None

    def __enter__(self):
        self.process = subprocess.Popen(
            [str(self.binary)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=None, bufsize=0,
            env={**os.environ, "KSW_NI_ROLE": self.ni_role,
                 "KSW_HID_ONLY": "1" if self.hid_only else "0",
                 "KSW_ALLOW_NO_SCREENS": "1" if self.allow_no_screens else "0"},
        )
        self.output_thread = threading.Thread(
            target=self._events, name="hardware-events", daemon=True
        )
        self.output_thread.start()
        if not self.ready.wait(timeout=75):
            self._terminate()
            raise RuntimeError("Hardware helper startup timed out; check stderr logs")
        if self.startup_error:
            self._terminate()
            raise RuntimeError(self.startup_error)
        return self

    def _events(self):
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                try:
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                kind = event.get("kind")
                if kind == "error" and not self.ready.is_set():
                    self.startup_error = str(event.get("message", "Hardware helper failed"))
                    self.ready.set()
                    continue
                if kind == "ready":
                    self.screens = bool(event.get("screens", True))
                    self.ready.set()
                try:
                    self.on_event(event)
                except Exception:
                    # A callback error should not terminate the stdout reader.
                    continue
        finally:
            if not self.ready.is_set():
                rc = self.process.poll()
                self.startup_error = f"Hardware helper exited before connecting (code {rc})"
                self.ready.set()

    def _send(self, command: bytes, payload: bytes):
        assert self.process is not None and self.process.stdin is not None
        with self.lock:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"Hardware helper is not running (exit code {self.process.returncode})"
                )
            try:
                self.process.stdin.write(command + payload)
            except (BrokenPipeError, OSError) as exc:
                raise RuntimeError(
                    "Hardware helper stopped while sending data; see its earlier error"
                ) from exc

    def set_lights(self, colors: bytes):
        if len(colors) != 61:
            raise ValueError("S61 MK2 requires 61 palette bytes")
        self._send(b"L", colors)

    def send_frame(self, rgba: bytes):
        if len(rgba) != FRAME_SIZE:
            raise ValueError(f"Expected {FRAME_SIZE} RGBA bytes; received {len(rgba)}")
        self._send(b"F", rgba)

    def _terminate(self):
        if not self.process:
            return
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        if self.process.stdin:
            self.process.stdin.close()
        if self.process.stdout:
            self.process.stdout.close()

    def __exit__(self, *_):
        if self.process and self.process.poll() is None:
            try:
                self.set_lights(bytes(61))
                self._send(b"Q", b"")
            except (OSError, RuntimeError):
                pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            if self.process.stdout:
                self.process.stdout.close()
