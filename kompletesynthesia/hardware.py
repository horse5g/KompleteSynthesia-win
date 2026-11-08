"""Optional standalone light-only HID backend; do not open alongside Encdr."""

from __future__ import annotations

VENDOR_ID = 0x17CC
PRODUCT_ID_S61_MK2 = 0x1620


class DirectLightGuide:
    def __init__(self):
        self.device = None

    def __enter__(self):
        import hid

        self.device = hid.device()
        self.device.open(VENDOR_ID, PRODUCT_ID_S61_MK2)
        self.device.write(bytes((0xA0, 0x00, 0x00)))
        self.set_lights(bytes(61))
        return self

    def set_lights(self, colors: bytes):
        if len(colors) != 61:
            raise ValueError("S61 MK2 requires exactly 61 palette bytes")
        if self.device is None:
            raise RuntimeError("Light Guide device is not open")
        self.device.write(b"\x81" + colors)

    def __exit__(self, *_):
        if self.device is not None:
            try:
                self.set_lights(bytes(61))
            finally:
                self.device.close()
                self.device = None
