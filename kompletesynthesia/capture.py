"""Synthesia window capture and 2x480x272 display composition on Windows 11.

Current backend is desktop capture (mss); a covered window cannot be mirrored.
The macOS app captured a window independently of its z-order, so WGC is a
planned replacement. No unsupported PrintWindow calls are used here.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

SCREEN_WIDTH = 960
SCREEN_HEIGHT = 272
PANEL_WIDTH = 480


def idle_screen():
    """Native-resolution standby screen, also used when mirroring is toggled off."""
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), "#111827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 4, 475, 267), outline="#2f7991", width=2)
    draw.rectangle((484, 4, 955, 267), outline="#2f7991", width=2)
    draw.text((90, 112), "KOMPLETE SYNTHESIA", fill="#dfedf7")
    draw.text((90, 137), "Windows 11 / S61 MK2", fill="#70acbe")
    draw.text((565, 112), "SYNTHESIA MIRROR", fill="#dfedf7")
    draw.text((565, 137), "Press TOP 5 to toggle", fill="#70acbe")
    return image


def _fit_to(image, size: tuple[int, int], mode: str):
    from PIL import Image
    width_target, height_target = size
    if mode == "stretch":
        return image.resize(size, Image.Resampling.LANCZOS)
    ratio = (min if mode == "fit" else max)(
        width_target / image.width, height_target / image.height
    )
    w, h = max(1, round(image.width * ratio)), max(1, round(image.height * ratio))
    resized = image.resize((w, h), Image.Resampling.LANCZOS)
    if mode == "fill":
        x, y = (w - width_target) // 2, (h - height_target) // 2
        return resized.crop((x, y, x + width_target, y + height_target))
    result = Image.new("RGB", size, "black")
    result.paste(resized, ((width_target - w) // 2, (height_target - h) // 2))
    return result


def fit_image(image, mode: str = "fit", layout: str = "span"):
    """Fit a PIL frame across both screens or only the left screen.

    span: 960x272 combined image (existing prototype default)
    left: original KompleteSynthesia-style left-screen mirror + standby right.
    """
    if mode not in ("fit", "fill", "stretch"):
        raise ValueError("capture mode must be fit, fill, or stretch")
    if layout not in ("span", "left"):
        raise ValueError("layout must be span or left")
    image = image.convert("RGB")
    if layout == "span":
        return _fit_to(image, (SCREEN_WIDTH, SCREEN_HEIGHT), mode)
    frame = idle_screen()
    frame.paste(_fit_to(image, (PANEL_WIDTH, SCREEN_HEIGHT), mode), (0, 0))
    return frame


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
    """Return first visible non-minimized top-level window with matching title."""
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
            buffer = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buffer, n + 1)
            if title_fragment.casefold() in buffer.value.casefold():
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
        raise RuntimeError("Synthesia window minimized or no longer available")
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise RuntimeError("Unable to locate Synthesia client area")
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise RuntimeError("Synthesia has an empty client area")
    return {"left": origin.x, "top": origin.y, "width": w, "height": h}


def grab_frame(sct, hwnd: int, mode: str = "fit", layout: str = "span"):
    from PIL import Image
    shot = sct.grab(client_region(hwnd))
    image = Image.frombytes("RGB", shot.size, shot.rgb)
    return fit_image(image, mode, layout)
