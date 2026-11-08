"""Visible Synthesia client-area capture and layout for the two MK2 displays."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

SCREEN_WIDTH = 960
SCREEN_HEIGHT = 272


def fit_image(image, mode: str = "fit"):
    """Convert a PIL image into the combined 960x272 RGB canvas."""
    from PIL import Image

    if mode not in ("fit", "fill", "stretch"):
        raise ValueError("capture mode must be fit, fill, or stretch")
    image = image.convert("RGB")
    if mode == "stretch":
        return image.resize((SCREEN_WIDTH, SCREEN_HEIGHT), Image.Resampling.LANCZOS)
    ratio = min(SCREEN_WIDTH / image.width, SCREEN_HEIGHT / image.height)
    if mode == "fill":
        ratio = max(SCREEN_WIDTH / image.width, SCREEN_HEIGHT / image.height)
    width, height = max(1, round(image.width * ratio)), max(1, round(image.height * ratio))
    resized = image.resize((width, height), Image.Resampling.LANCZOS)
    if mode == "fill":
        x, y = (width - SCREEN_WIDTH) // 2, (height - SCREEN_HEIGHT) // 2
        return resized.crop((x, y, x + SCREEN_WIDTH, y + SCREEN_HEIGHT))
    result = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), (0, 0, 0))
    result.paste(resized, ((SCREEN_WIDTH - width) // 2, (SCREEN_HEIGHT - height) // 2))
    return result


def diagnostic_pattern():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), "#101820")
    painter = ImageDraw.Draw(img)
    painter.rectangle((0, 0, 479, 271), outline="cyan", width=4)
    painter.rectangle((480, 0, 959, 271), outline="orange", width=4)
    painter.text((125, 115), "S61 MK2 - LEFT", fill="white")
    painter.text((625, 115), "S61 MK2 - RIGHT", fill="white")
    return img


def _win_user32():
    if not hasattr(ctypes, "WinDLL"):
        raise RuntimeError("Synthesia window capture requires Windows 11")
    return ctypes.WinDLL("user32", use_last_error=True)


def find_window(title_fragment: str) -> int | None:
    """Return the first visible, non-minimized top-level window matching title."""
    user32 = _win_user32()
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    matches: list[int] = []

    @callback_type
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buff = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buff, n + 1)
            if title_fragment.casefold() in buff.value.casefold():
                matches.append(hwnd)
                return False
        return True

    user32.EnumWindows(visit, 0)
    return matches[0] if matches else None


def client_region(hwnd: int) -> dict[str, int]:
    user32 = _win_user32()
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.IsIconic.argtypes = [wintypes.HWND]
    rect = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    if user32.IsIconic(hwnd) or not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("Synthesia window is minimized or no longer available")
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise RuntimeError("Unable to locate Synthesia client area")
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise RuntimeError("Synthesia has an empty client area")
    return {"left": origin.x, "top": origin.y, "width": width, "height": height}


def grab_frame(sct, hwnd: int, mode: str):
    """Visible-window capture: another window covering Synthesia will be captured."""
    from PIL import Image

    shot = sct.grab(client_region(hwnd))
    image = Image.frombytes("RGB", shot.size, shot.rgb)
    return fit_image(image, mode)
