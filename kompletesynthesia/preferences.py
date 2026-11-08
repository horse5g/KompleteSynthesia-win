"""Persistent settings and MK2 palette, based on KompleteSynthesia's preferences.

Only JSON data is stored in the user's local application-data directory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
import os
from pathlib import Path

@dataclass
class ColorPalette:
    unpressed: int = 0x00
    pressed: int = 0x47
    left: int = 0x2D
    left_thumb: int = 0x2F
    left_pressed: int = 0x2F
    right: int = 0x1D
    right_thumb: int = 0x1F
    right_pressed: int = 0x1F

@dataclass
class Settings:
    palette: ColorPalette = field(default_factory=ColorPalette)
    midi_port: str | None = None
    keyboard_midi_port: str | None = None
    controls_enabled: bool = True
    focus_synthesia: bool = True
    mirror_enabled: bool = True
    capture_mode: str = "fit"
    display_layout: str = "span"
    fps: int = 12

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        if not isinstance(data, dict):
            raise ValueError("Settings must be a JSON object")
        obj = cls()
        for f in fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            if f.name == "palette":
                if not isinstance(value, dict):
                    raise ValueError("palette must be an object")
                kwargs = {}
                allowed = {p.name for p in fields(ColorPalette)}
                for name, color in value.items():
                    if name not in allowed:
                        continue
                    if type(color) is not int or not 0 <= color <= 255:
                        raise ValueError(f"palette.{name} must be a byte, 0 through 255")
                    kwargs[name] = color
                obj.palette = ColorPalette(**kwargs)
            elif f.name in ("midi_port", "keyboard_midi_port"):
                if value is not None and not isinstance(value, str):
                    raise ValueError(f"{f.name} must be a string or null")
                setattr(obj, f.name, value)
            elif f.name in ("controls_enabled", "focus_synthesia", "mirror_enabled"):
                if type(value) is not bool:
                    raise ValueError(f"{f.name} must be true or false")
                setattr(obj, f.name, value)
            elif f.name == "fps":
                if type(value) is not int or not 1 <= value <= 30:
                    raise ValueError("fps must be between 1 and 30")
                obj.fps = value
            elif f.name == "capture_mode":
                if value not in ("fit", "fill", "stretch"):
                    raise ValueError("capture_mode must be fit, fill or stretch")
                obj.capture_mode = value
            elif f.name == "display_layout":
                if value not in ("span", "left"):
                    raise ValueError("display_layout must be span or left")
                obj.display_layout = value
        return obj

    def to_dict(self) -> dict:
        return asdict(self)


def config_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".config"))
    return root / "KompleteSynthesia-win" / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or config_path()
    if not path.exists():
        return Settings()
    try:
        return Settings.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid settings file {path}: {exc}") from exc


def save_settings(settings: Settings, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(settings.to_dict(), indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    return path
