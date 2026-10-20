"""Floating 5.x menu (roadmap 5.4.0), drawn like the owner's reference image.

A borderless window holding one canvas: a rounded, softly shadowed surface with a hairline border, a line icon and
a tracked-caps label per row, and a blue rounded highlight on the active row. Disabled rows are dimmed and show
why in the hint line. Mouse: hover highlights, click runs. Keyboard: ↑ ↓ move, Enter runs, Esc closes. It opens
with a short fade + slide (180 ms) on the shared motion clock, or at once under *Reduce motion*.

The widget only shows rows and calls ``on_pick(row)``; it never touches project state itself.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from . import task_menu
from .assets import Assets
from .tokens5 import GEOMETRY, MOTION, font5, palette5

ROW_H = 32
WIDTH = 214
PAD = 6
SHADOW = 10
HINT_H = 26


class FloatingMenu:
    """One open menu at a time per owner widget; ``close()`` is safe to call twice."""

    def __init__(self, owner: tk.Misc, assets: Assets, rows: list[dict[str, Any]], *,
                 on_pick: Callable[[dict[str, Any]], Any], motion: Any = None, title: str = "") -> None:
        self.owner, self.assets, self.rows, self.on_pick, self.motion = owner, assets, rows, on_pick, motion
        self.title = title
        self.index = task_menu.first_enabled(rows)
        self.closed = False
        s = assets.scale
        p = palette5(assets.theme)
        self.s, self.p = s, p
        self.w = int(WIDTH * s)
        self.head = int(22 * s) if title else 0
        self.h = int(2 * PAD * s + self.head + ROW_H * s * len(rows) + HINT_H * s)
        self.top = tk.Toplevel(owner)
        self.top.withdraw()
        self.top.overrideredirect(True)
        try:
            self.top.attributes("-topmost", True)
        except tk.TclError:
            pass
        self._transparent = ""
        try:  # Windows: a colour key makes the shadow corners see-through
            self.top.attributes("-transparentcolor", "#010203")
            self._transparent = "#010203"
        except tk.TclError:
            pass
        # a soft shadow only where the corners can be see-through (Windows); elsewhere a clean hairline edge
        self.shadow = SHADOW if self._transparent else 0
        sh = int(self.shadow * s)
        bg = self._transparent or p["menu"]
        self.canvas = tk.Canvas(self.top, width=self.w + 2 * sh, height=self.h + 2 * sh, highlightthickness=0, bd=0,
                                background=bg)
        self.canvas._aiwb_keep_colours = True  # type: ignore[attr-defined]
        self.canvas.pack()
        self.ox = self.oy = sh
        self.row_items: list[tuple[int, int, int]] = []
        self._draw()
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", lambda _e: None)
        self.canvas.bind("<ButtonRelease-1>", self._click)
        for seq, fn in (("<Up>", lambda _e: self.step(-1)), ("<Down>", lambda _e: self.step(1)),
                        ("<Return>", lambda _e: self.activate()), ("<KP_Enter>", lambda _e: self.activate()),
                        ("<Escape>", lambda _e: self.close()), ("<FocusOut>", self._focus_out)):
            self.top.bind(seq, fn)

    # -- drawing
    def _draw(self) -> None:
        c, s, p = self.canvas, self.s, self.p
        c.delete("all")
        surf = self.assets.sprite("panel", w=self.w, h=self.h, r=GEOMETRY["radius_menu"], role="menu",
                                  border="menu_border", shadow=self.shadow)
        c.create_image(0, 0, image=surf, anchor="nw", tags=("surface",))
        y = self.oy + PAD * s
        if self.title:
            c.create_text(self.ox + 14 * s, y + self.head / 2, text=self.title, anchor="w", fill=p["text_faint"],
                          font=font5("caption", s), tags=("title",))
            y += self.head
        self.row_items = []
        self.row_y: list[float] = []
        for i, row in enumerate(self.rows):
            self.row_y.append(y)
            col = p["text"] if row["enabled"] else p["text_faint"]
            ic = c.create_image(self.ox + 22 * s, y + ROW_H * s / 2,
                                image=self.assets.icon(row["icon"], 16, color=col), tags=("row", f"row{i}"))
            tx = c.create_text(self.ox + 40 * s, y + ROW_H * s / 2, text=row["label"], anchor="w", fill=col,
                               font=font5("label_caps", s), tags=("row", f"row{i}"))
            self.row_items.append((ic, tx, i))
            y += ROW_H * s
        c.create_line(self.ox + 10 * s, y + 2 * s, self.ox + self.w - 10 * s, y + 2 * s, fill=p["line_soft"],
                      tags=("sep",))
        self.hint = c.create_text(self.ox + 14 * s, y + (HINT_H * s) / 2 + 2 * s, anchor="w", fill=p["text_dim"],
                                  font=font5("caption", s), width=self.w - 24 * s, tags=("hint",))
        self._highlight()

    def _highlight(self) -> None:
        c, s, p = self.canvas, self.s, self.p
        c.delete("hl")
        for ic, tx, i in self.row_items:
            row = self.rows[i]
            on = i == self.index and row["enabled"]
            col = p["active_text"] if on else (p["text"] if row["enabled"] else p["text_faint"])
            c.itemconfigure(tx, fill=col)
            c.itemconfigure(ic, image=self.assets.icon(row["icon"], 16, color=col))
        if 0 <= self.index < len(self.rows):
            y = self.row_y[self.index]
            dark = self.assets.theme == "midnight"  # Midnight: deep-blue row + blue edge; Daylight: solid blue row
            hl = self.assets.sprite("panel", w=int(self.w - 2 * PAD * s), h=int(ROW_H * s - 4 * s),
                                    r=GEOMETRY["radius_ctl"], role="selection" if dark else "active",
                                    border="active" if dark else "active_hi")
            item = c.create_image(self.ox + PAD * s, y + 2 * s, image=hl, anchor="nw", tags=("hl",))
            c.tag_raise(item, "surface")
            c.tag_raise("row")
        row = self.rows[self.index] if 0 <= self.index < len(self.rows) else None
        c.itemconfigure(self.hint, text=(row or {}).get("hint", "") if row else "Nothing to do for this task now.")

    # -- showing
    def popup(self, x_root: int, y_root: int) -> "FloatingMenu":
        """Show near the pointer, kept on screen; fade + slide in on the motion clock."""
        sw, shh = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
        tw, th = self.w + 2 * self.ox, self.h + 2 * self.oy
        x = min(max(0, x_root + int(8 * self.s) - self.ox), sw - tw)
        y = min(max(0, y_root - int(10 * self.s) - self.oy), shh - th)
        self.x, self.y = x, y
        lift = int(6 * self.s)
        self.top.geometry(f"+{x}+{y + lift}")
        self.top.deiconify()
        self.top.lift()
        try:
            self.top.focus_force()
        except tk.TclError:
            pass
        alpha_ok = True
        try:
            self.top.attributes("-alpha", 0.0)
        except tk.TclError:
            alpha_ok = False

        def step(t: float) -> None:
            if self.closed:
                return
            if alpha_ok:
                try:
                    self.top.attributes("-alpha", t)
                except tk.TclError:
                    pass
            self.top.geometry(f"+{x}+{y + round(lift * (1 - t))}")

        if self.motion is not None:
            self.motion.tween("menu:open", 0.0, 1.0, MOTION["menu_ms"], step, ease="out", alive=self.top.winfo_exists)
        else:
            step(1.0)
        return self

    # -- interaction
    def row_at(self, y: float) -> int:
        for i, ry in enumerate(getattr(self, "row_y", [])):
            if ry <= y < ry + ROW_H * self.s:
                return i
        return -1

    def _hover(self, e: Any) -> None:
        i = self.row_at(e.y)
        if i != self.index and i >= 0:
            self.index = i
            self._highlight()

    def _click(self, e: Any) -> None:
        i = self.row_at(e.y)
        if i >= 0:
            self.index = i
            self.activate()

    def step(self, delta: int) -> None:
        self.index = task_menu.move(self.rows, self.index, delta)
        self._highlight()

    def activate(self) -> Any:
        if not (0 <= self.index < len(self.rows)) or not self.rows[self.index]["enabled"]:
            return None
        row = self.rows[self.index]
        self.close()
        return self.on_pick(row)

    def _focus_out(self, _e: Any) -> None:
        self.top.after(60, self._maybe_close)

    def _maybe_close(self) -> None:
        if self.closed:
            return
        try:
            f = self.top.focus_get()
        except (KeyError, tk.TclError):
            f = None
        if f is None:
            self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.motion is not None:
            self.motion.stop("menu:open")
        try:
            self.top.destroy()
        except tk.TclError:
            pass
