"""Windows Tk settings editor for the ported KompleteSynthesia preferences.

Tk is bundled with standard Windows Python builds; no GUI dependencies needed.
Settings changes apply on the next run, not while the bridge is running.
"""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from .preferences import ColorPalette, load_settings, save_settings


def show_preferences(path: Path) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    settings = load_settings(path)
    root = tk.Tk()
    root.title("KompleteSynthesia-win | Settings")
    root.resizable(False, False)
    container = ttk.Frame(root, padding=16)
    container.grid(sticky="nsew")
    ttk.Label(container, text="S61 MK2 Light Guide", font=("Segoe UI", 12, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )
    color_values = {}
    for index, f in enumerate(fields(ColorPalette), 1):
        ttk.Label(container, text=f.name.replace("_", " ").title()).grid(
            row=index, column=0, sticky="w", padx=(0, 20), pady=3
        )
        value = tk.StringVar(value=f"0x{getattr(settings.palette, f.name):02X}")
        color_values[f.name] = value
        ttk.Entry(container, textvariable=value, width=12).grid(
            row=index, column=1, sticky="e"
        )

    base_row = len(color_values) + 2
    controls = tk.BooleanVar(value=settings.controls_enabled)
    focus = tk.BooleanVar(value=settings.focus_synthesia)
    mirror = tk.BooleanVar(value=settings.mirror_enabled)
    ttk.Checkbutton(container, text="Enable keyboard shortcuts",
                    variable=controls).grid(row=base_row, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(container, text="Activate Synthesia before shortcuts",
                    variable=focus).grid(row=base_row+1, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(container, text="Mirror Synthesia screens",
                    variable=mirror).grid(row=base_row+2, column=0, columnspan=2, sticky="w")
    layout = tk.StringVar(value=settings.display_layout)
    ttk.Label(container, text="Display layout").grid(row=base_row+3, column=0, sticky="w")
    ttk.Combobox(container, textvariable=layout, state="readonly",
                 values=("span", "left"), width=10).grid(row=base_row+3, column=1, sticky="e")
    capture = tk.StringVar(value=settings.capture_mode)
    ttk.Label(container, text="Capture scaling").grid(row=base_row+4, column=0, sticky="w")
    ttk.Combobox(container, textvariable=capture, state="readonly",
                 values=("fit", "fill", "stretch"), width=10).grid(
                     row=base_row+4, column=1, sticky="e")
    fps = tk.StringVar(value=str(settings.fps))
    ttk.Label(container, text="Frames per second (1-30)").grid(row=base_row+5, column=0, sticky="w")
    ttk.Entry(container, textvariable=fps, width=12).grid(row=base_row+5, column=1, sticky="e")
    ttk.Label(container, text="Palette values are hardware codes, not RGB.",
              foreground="#777777").grid(
                  row=base_row+6, column=0, columnspan=2, pady=(8, 2), sticky="w")

    def save():
        try:
            values = settings.to_dict()
            values["palette"] = {name: int(var.get().strip(), 0)
                                 for name, var in color_values.items()}
            values.update(
                controls_enabled=controls.get(),
                focus_synthesia=focus.get(),
                mirror_enabled=mirror.get(),
                display_layout=layout.get(),
                capture_mode=capture.get(),
                fps=int(fps.get()),
            )
            save_settings(type(settings).from_dict(values), path)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Cannot save settings", str(exc), parent=root)
            return
        messagebox.showinfo("Saved", "Settings saved. Restart the bridge to apply changes.",
                            parent=root)
        root.destroy()

    ttk.Button(container, text="Save settings", command=save).grid(
        row=base_row+7, column=0, columnspan=2, sticky="ew", pady=(12, 0)
    )
    root.mainloop()
