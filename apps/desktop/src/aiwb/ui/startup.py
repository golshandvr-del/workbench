"""Fast, crisp start (roadmap 5.0.0).

* :func:`enable_dpi_awareness` — on Windows the process declares itself per-monitor DPI aware *before* Tk starts,
  so Windows stops bitmap-stretching the window (blurry text) and Tk measures real pixels.
* :func:`ui_scale` — the DPI scale (1.0 = 96 dpi) used for every 5.x sprite and geometry token.
* :class:`Splash` — a small borderless card drawn within milliseconds of launch while the rest of the app is
  built, so the user sees the app at once instead of an empty wait.

Nothing here touches project data.
"""
from __future__ import annotations

import sys
import tkinter as tk
from typing import Any

from .tokens5 import font5, palette5


def enable_dpi_awareness() -> str:
    """Declare DPI awareness (Windows only). Returns the mode that worked, or "" (never raises)."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        try:
            # PER_MONITOR_AWARE_V2 (Windows 10 1703+)
            if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return "per-monitor-v2"
        except (AttributeError, OSError):
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return "per-monitor"
        except (AttributeError, OSError):
            pass
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except Exception:  # noqa: BLE001 — a missing API must never stop the app
        return ""


def ui_scale(root: tk.Misc) -> float:
    """DPI scale of the window (1.0, 1.25, 1.5, 2.0 …), rounded to a quarter and clamped to 1–3."""
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except (tk.TclError, ValueError):
        return 1.0
    s = round(dpi / 96.0 * 4) / 4
    return min(3.0, max(1.0, s))


class Splash:
    """A borderless start card centred on the screen; :meth:`close` removes it."""

    def __init__(self, root: tk.Tk, *, title: str, version: str, theme: str = "midnight") -> None:
        p = palette5(theme)
        self.top: tk.Toplevel | None = None
        try:
            top = tk.Toplevel(root)
            top.overrideredirect(True)
            top.configure(background=p["line"])
            s = ui_scale(root)
            w, h = int(360 * s), int(150 * s)
            x = (root.winfo_screenwidth() - w) // 2
            y = (root.winfo_screenheight() - h) // 2
            top.geometry(f"{w}x{h}+{x}+{y}")
            c = tk.Canvas(top, width=w - 2, height=h - 2, background=p["panel"], highlightthickness=0, bd=0)
            c.place(x=1, y=1)
            self._star(c, 40 * s, 52 * s, 11 * s, p["active_hi"])
            c.create_text(62 * s, 52 * s, text=title, anchor="w", fill=p["text"], font=font5("title", 1.25))
            c.create_text(62 * s, 76 * s, text=f"v{version}", anchor="w", fill=p["text_faint"], font=font5("mono"))
            self.bar = c.create_rectangle(24 * s, h - 34 * s, 24 * s, h - 32 * s, fill=p["active"], width=0)
            c.create_text(24 * s, h - 20 * s, text="Starting…", anchor="w", fill=p["text_dim"], font=font5("small"))
            self.canvas, self.width, self.scale = c, w, s
            self.top = top
            top.update()
        except tk.TclError:
            self.top = None

    @staticmethod
    def _star(c: tk.Canvas, x: float, y: float, r: float, color: str) -> None:
        k = r * 0.28
        c.create_polygon(x, y - r, x + k, y - k, x + r, y, x + k, y + k, x, y + r, x - k, y + k, x - r, y, x - k, y - k,
                         fill=color, outline="")

    def progress(self, fraction: float) -> None:
        if self.top is None:
            return
        try:
            s = self.scale
            x1 = 24 * s + (self.width - 48 * s) * max(0.0, min(1.0, fraction))
            x0, y0, _x1, y1 = self.canvas.coords(self.bar)
            self.canvas.coords(self.bar, x0, y0, x1, y1)
            self.top.update_idletasks()
        except tk.TclError:
            pass

    def close(self) -> None:
        top, self.top = self.top, None
        if top is not None:
            try:
                top.destroy()
            except tk.TclError:
                pass

    def __enter__(self) -> "Splash":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()
