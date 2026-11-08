"""S61 Mk2 control mappings ported from macOS KompleteSynthesia.

The router is OS-independent; only send_windows_action uses Windows SendInput.
Shortcut delivery is guarded by Synthesia window focus, so button presses
cannot accidentally type into another application.
"""
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Action:
    kind: str
    value: str | int | None = None


BUTTONS = {
    "play": Action("key", "space"),
    "encoder_main_press": Action("key", "enter"),
    "encoder_main_left": Action("key", "left"),
    "encoder_main_right": Action("key", "right"),
    "encoder_main_up": Action("key", "up"),
    "encoder_main_down": Action("key", "down"),
    "page_left": Action("key", "z"),
    "page_right": Action("key", "x"),
    "top_1": Action("key", "escape"),
    "top_2": Action("key", "f2"),
    "top_3": Action("key", "f3"),
    "top_4": Action("key", "f4"),
    "top_5": Action("toggle_mirror"),
    "clear": Action("reset"),
    "scene": Action("launch"),
    "setup": Action("settings"),
}

class ControlRouter:
    def route(self, event: dict) -> Action | None:
        kind = event.get("kind")
        name = event.get("name")
        if kind == "button":
            return BUTTONS.get(name) if event.get("pressed") is True else None
        if kind != "encoder":
            return None
        try:
            delta = int(event.get("delta", 0))
        except (ValueError, TypeError, OverflowError):
            return None
        if not delta:
            return None
        if name == "encoder_main":
            return Action("wheel", -delta)
        if name == "encoder_1":
            return Action("volume", 1 if delta > 0 else -1)
        return None


VK = {
    "space": 0x20, "enter": 0x0D, "left": 0x25, "right": 0x27,
    "up": 0x26, "down": 0x28, "escape": 0x1B,
    "z": 0x5A, "x": 0x58, "f2": 0x71, "f3": 0x72, "f4": 0x73,
}

def send_windows_action(action: Action, synthesia_hwnd: int | None,
                        focus_synthesia: bool = True) -> bool:
    """Send a routed key/wheel/volume event with native Win32 SendInput.

    Return False if the Synthesia window isn't frontmost and can't be activated.
    Only the volume hotkey is global.
    """
    import ctypes
    from ctypes import wintypes

    if not hasattr(ctypes, "WinDLL"):
        raise OSError("Controls require Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL

    if action.kind not in ("key", "wheel", "volume"):
        return False
    if action.kind != "volume":
        if not synthesia_hwnd:
            return False
        if user32.GetForegroundWindow() != synthesia_hwnd:
            if not focus_synthesia:
                return False
            user32.SetForegroundWindow(synthesia_hwnd)
        if user32.GetForegroundWindow() != synthesia_hwnd:
            return False

    class KeyInput(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class HardwareInput(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class InputData(ctypes.Union):
        _fields_ = [("ki", KeyInput), ("mi", MouseInput), ("hi", HardwareInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("data", InputData)]

    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    if action.kind == "wheel":
        count = max(-10, min(10, int(action.value)))
        wheel = MouseInput(0, 0, ctypes.c_uint32(120 * count).value, 0x0800, 0, 0)
        inputs = (Input * 1)(Input(0, InputData(mi=wheel)))
    else:
        vk = VK[action.value] if action.kind == "key" else (
            0xAF if int(action.value) > 0 else 0xAE
        )
        press = KeyInput(vk, 0, 0, 0, 0)
        release = KeyInput(vk, 0, 0x0002, 0, 0)
        inputs = (Input * 2)(
            Input(1, InputData(ki=press)),
            Input(1, InputData(ki=release)),
        )
    return user32.SendInput(len(inputs), inputs, ctypes.sizeof(Input)) == len(inputs)
