"""Settings › App Map (roadmap 5.5.0): the live App Map drawn inside the application.

Same layout as ``docs/design/ui_map.png`` (:func:`ui_map.layout`), drawn on a Tk Canvas: curved connectors, rounded
kind-coloured pills, a counts line and the audit result. Scroll with the wheel (Shift = sideways), drag to pan,
``+``/``-`` to zoom, a filter box keeps only the branches whose labels contain the text.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from . import ui_map
from .tokens5 import palette5


def filtered(tree: dict[str, Any], text: str) -> dict[str, Any]:
    """The tree reduced to the branches whose label contains ``text`` (case-insensitive); ancestors kept."""
    q = text.strip().lower()
    if not q:
        return tree

    def rec(n: dict[str, Any]) -> dict[str, Any] | None:
        kids = [k for k in (rec(c) for c in n["children"]) if k is not None]
        if kids or q in n["label"].lower():
            return {"label": n["label"], "kind": n["kind"],
                    "children": kids if kids else (n["children"] if q in n["label"].lower() else [])}
        return None
    return rec(tree) or ui_map.node(tree["label"], tree["kind"])


def summary(tree: dict[str, Any]) -> str:
    pages = ui_map.pages(tree)
    total = sum(1 for _p, n in ui_map.iter_nodes(tree) if n["kind"] in ui_map.COMMAND_KINDS)
    problems = ui_map.audit(tree)
    state = "balanced" if not problems else f"{len(problems)} balance issue(s)"
    return f"{len(pages)} pages · {total} commands · {state}"


class MapView(ttk.Frame):
    """A scrollable, zoomable drawing of an App Map tree."""

    def __init__(self, parent: tk.Misc, tree: dict[str, Any], *, theme: str = "midnight") -> None:
        super().__init__(parent)
        self.tree = tree
        self.palette = palette5(theme)
        self.scale = 1.0
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Filter").pack(side="left")
        self.filter_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.filter_var, width=28)
        entry.pack(side="left", padx=(6, 10))
        self.filter_var.trace_add("write", lambda *_: self.draw())
        ttk.Button(bar, text="Zoom out", command=lambda: self.zoom(1 / 1.2)).pack(side="left")
        ttk.Button(bar, text="Zoom in", command=lambda: self.zoom(1.2)).pack(side="left", padx=(4, 0))
        self.summary_var = tk.StringVar(value=summary(tree))
        ttk.Label(bar, textvariable=self.summary_var).pack(side="right")
        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(holder, background=self.palette["field"], highlightthickness=0, borderwidth=0)
        ys = ttk.Scrollbar(holder, orient="vertical", command=self.canvas.yview)
        xs = ttk.Scrollbar(holder, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        c = self.canvas
        c.bind("<MouseWheel>", lambda e: c.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        c.bind("<Shift-MouseWheel>", lambda e: c.xview_scroll(-1 if e.delta > 0 else 1, "units"))
        c.bind("<Button-4>", lambda _e: c.yview_scroll(-1, "units"))
        c.bind("<Button-5>", lambda _e: c.yview_scroll(1, "units"))
        c.bind("<ButtonPress-1>", lambda e: c.scan_mark(e.x, e.y))
        c.bind("<B1-Motion>", lambda e: c.scan_dragto(e.x, e.y, gain=1))
        for key, f in (("<plus>", 1.2), ("<equal>", 1.2), ("<minus>", 1 / 1.2)):
            c.bind(key, lambda _e, f=f: self.zoom(f))
        self.boxes = 0
        self.draw()

    def zoom(self, factor: float) -> None:
        self.scale = max(0.5, min(2.0, self.scale * factor))
        self.draw()

    def draw(self) -> None:
        c, p, s = self.canvas, self.palette, self.scale
        c.delete("all")
        tree = filtered(self.tree, self.filter_var.get())
        g = ui_map.layout(tree, col_w=int(210 * s), row_h=max(14, int(22 * s)))
        cw, rh = g["col_w"], g["row_h"]
        bw, bh = cw - int(28 * s), max(12, int(18 * s))
        font = ("Segoe UI", max(7, int(9 * s)))
        bold = ("Segoe UI", max(7, int(9 * s)), "bold")
        for a, b in g["edges"]:
            pa, pb = g["boxes"][a], g["boxes"][b]
            x0, y0, x1, y1 = pa["x"] + bw, pa["y"], pb["x"], pb["y"]
            mx = (x0 + x1) / 2
            c.create_line(x0, y0, mx, y0, mx, y1, x1, y1, smooth=True, splinesteps=16, fill=p["text_faint"], width=1)
        for bx in g["boxes"]:
            col = p[ui_map.KIND_ROLE[bx["kind"]]]
            strong = bx["kind"] in ("app", "area", "page", "section", "tab")
            x, y = bx["x"], bx["y"]
            self._pill(x, y - bh / 2, x + bw, y + bh / 2, p["raised"] if strong else p["field"], col, 2 if strong else 1)
            label = bx["label"] if len(bx["label"]) <= 30 else bx["label"][:29] + "…"
            c.create_text(x + 9 * s, y, text=label, anchor="w", fill=col if strong else p["text"],
                          font=bold if strong else font, tags=("label",))
        self.boxes = len(g["boxes"])
        c.configure(scrollregion=(0, 0, g["width"], g["height"]))
        self.summary_var.set(summary(tree))
        _ = rh

    def _pill(self, x0: float, y0: float, x1: float, y1: float, fill: str, outline: str, width: int) -> None:
        r = (y1 - y0) / 2
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
               x0, y1 - r, x0, y0 + r, x0, y0]
        self.canvas.create_polygon(pts, smooth=True, fill=fill, outline=outline, width=width)


def open_window(parent: tk.Misc, tree: dict[str, Any], *, theme: str = "midnight") -> tk.Toplevel:
    """Settings › App Map…: a resizable window with the drawn map."""
    win = tk.Toplevel(parent)
    win.title("App Map — every place and every command")
    win.geometry("1100x720")
    win.configure(background=palette5(theme)["window"])
    view = MapView(win, tree, theme=theme)
    view.pack(fill="both", expand=True, padx=10, pady=10)
    win.view = view  # type: ignore[attr-defined]
    win.bind("<Escape>", lambda _e: win.destroy())
    view.canvas.focus_set()
    return win
