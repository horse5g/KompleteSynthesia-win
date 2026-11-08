"""Binary stdin/stdout IPC for the Encdr screen/control helper process.

Commands: 'L' + 61-byte light palette; 'F' + 960x272 RGBA pixels; 'Q' quit.
Responses: newline-delimited JSON events on stdout; diagnostics on stderr.
"""

from __future__ import annotations

import json
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
        base / "bin" / "encdr_bridge.exe",
        base / "native" / "encdr_bridge" / "target" / "release" / "encdr_bridge.exe",
        base / "native" / "encdr_bridge" / "target" / "debug" / "encdr_bridge.exe",
    ):
        if path.is_file():
            return path
    raise FileNotFoundError("Encdr helper missing. Download the Windows build artifact or compile native/encdr_bridge.")


class EncdrBridge:
    def __init__(self, binary: str | None = None, on_event=None):
        self.binary = find_bridge(binary)
        self.on_event = on_event or (lambda event: None)
        self.process: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.output_thread: threading.Thread | None = None

    def __enter__(self):
        self.process = subprocess.Popen(
            [str(self.binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=None, bufsize=0,
        )
        self.output_thread = threading.Thread(target=self._events, name="hardware-events", daemon=True)
        self.output_thread.start()
        return self

    def _events(self):
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            try:
                self.on_event(json.loads(line))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue

    def _send(self, command: bytes, payload: bytes):
        assert self.process is not None and self.process.stdin is not None
        with self.lock:
            if self.process.poll() is not None:
                raise RuntimeError(f"Encdr helper exited (code {self.process.returncode})")
            self.process.stdin.write(command + payload)

    def set_lights(self, colors: bytes):
        if len(colors) != 61:
            raise ValueError("S61 MK2 requires 61 palette bytes")
        self._send(b"L", colors)

    def send_frame(self, rgba: bytes):
        if len(rgba) != FRAME_SIZE:
            raise ValueError(f"Expected {FRAME_SIZE} RGBA bytes; received {len(rgba)}")
        self._send(b"F", rgba)

    def __exit__(self, *_):
        if self.process:
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
            if self.process.stdin:
                self.process.stdin.close()
            if self.process.stdout:
                self.process.stdout.close()
