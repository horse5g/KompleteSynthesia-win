"""Diagnostic probes for the two Native Instruments Windows named-pipe endpoints.

This module does not use WinUSB and does not modify drivers or firmware.
Version probes are read-only. An optional device-connect probe creates a
short-lived bootstrap registration which is immediately disconnected.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import struct
from typing import Callable

PIPES = (
    "com.native-instruments.NIHostIntegrationAgent",
    "NIHWMainHandler",
)
VERSION_MESSAGE = struct.pack("<I", 0x03536756)
TRUE_WORD = struct.pack("<I", 0x74727565)
ROLE_KONTROL = 0x4E694B4B  # "KKiN", from DrivenByKate / librebellion
ROLE_MASCHINE = 0x4E694D32  # "2MiN", the current Encdr default
PRODUCT_S61_MK2 = 0x1620


def device_connect(
    role: int, product: int = PRODUCT_S61_MK2, terminated_serial: bool = True
) -> bytes:
    """Build a device bootstrap frame with either Windows or legacy serial framing.

    DrivenByKate sends 5 words with serial_len=1 and a trailing null even
    without a specific serial. Earlier Encdr sent serial_len=0 with no null.
    """
    packet = struct.pack(
        "<IIIII", 0x03447500, product, role, 0x70726D79,
        1 if terminated_serial else 0,
    )
    return packet + (b"\x00" if terminated_serial else b"")


def describe_reply(reply: bytes) -> str:
    """Return diagnostics without exposing device serials or generated pipe names."""
    if not reply:
        return "empty response"
    prefix = reply[:min(len(reply), 16)].hex(" ")
    if reply.startswith(TRUE_WORD):
        return f"accepted (len={len(reply)}, first bytes={prefix})"
    if len(reply) == 4:
        return f"four-byte refusal/status (hex={prefix}, ascii={reply.decode('ascii', 'replace')!r})"
    if len(reply) == 8:
        return f"8-byte response (hex={prefix}; not a registration-acceptance marker)"
    return f"unexpected response (len={len(reply)}, first bytes={prefix})"


def call_named_pipe(name: str, message: bytes, timeout_ms: int = 2500) -> bytes:
    """Perform one request/reply using Windows CallNamedPipeW.

    CallNamedPipeW opens a *temporary* pipe instance, performs the transaction
    and closes it. Do not use it for the long-lived display protocol.
    """
    if not hasattr(ctypes, "WinDLL"):
        raise OSError("Native Instruments pipe diagnostics require Windows")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = kernel32.CallNamedPipeW
    fn.argtypes = (
        wintypes.LPCWSTR,
        ctypes.c_void_p, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
    )
    fn.restype = wintypes.BOOL
    request = ctypes.create_string_buffer(message)
    response = ctypes.create_string_buffer(4096)
    read = wintypes.DWORD()
    path = rf"\\.\pipe\{name}"
    ok = fn(path, ctypes.byref(request), len(message),
            ctypes.byref(response), len(response),
            ctypes.byref(read), timeout_ms)
    if not ok:
        err = ctypes.get_last_error()
        raise OSError(err, f"{path}: {ctypes.FormatError(err)}")
    return bytes(response.raw[:read.value])


def diagnostics(
    probe_connections: bool = False,
    exchange: Callable[[str, bytes], bytes] = call_named_pipe,
) -> list[str]:
    lines = [
        "Native Instruments named-pipe diagnostics",
        "Version probes are read-only; no USB drivers are changed.",
    ]
    for pipe in PIPES:
        lines.append(f"Pipe: {pipe}")
        try:
            lines.append(f"  version: {describe_reply(exchange(pipe, VERSION_MESSAGE))}")
        except OSError as exc:
            lines.append(f"  version: unavailable ({exc})")
        if not probe_connections:
            continue
        for label, role in (("Komplete Kontrol (KKiN)", ROLE_KONTROL),
                            ("Maschine (NiM2)", ROLE_MASCHINE)):
            for framing, terminated in (("nul-terminated-21", True),
                                         ("zero-length-20", False)):
                try:
                    result = exchange(pipe, device_connect(role, terminated_serial=terminated))
                    lines.append(f"  connect {label} [{framing}]: {describe_reply(result)}")
                except OSError as exc:
                    lines.append(f"  connect {label} [{framing}]: unavailable ({exc})")
    if not probe_connections:
        lines.append("For temporary client-registration probes, add --probe-ni-handshakes.")
    else:
        lines.append(
            "Client-registration probes are diagnostic only; successful bootstrap "
            "does not prove the screens can be driven."
        )
    return lines
