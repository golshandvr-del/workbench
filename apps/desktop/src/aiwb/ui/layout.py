"""Robust, symmetric layout helpers (roadmap 3.1.0, problem P2).

* :func:`place_dialog` — size a dialog to fit the screen work area, centre it on
  its parent and clamp it so no edge leaves the screen; the minimum size never
  exceeds the screen either.
* :class:`FlowBar` / :func:`flow` — a toolbar that wraps its buttons onto new
  rows instead of pushing them out of the window.
* :func:`auto_flow` — converts every existing "row of controls" (a frame whose
  packed children are all simple controls side by side) into a FlowBar, and
  makes wrapped hint labels follow the width of their container.
* :class:`ScrollPage` — a vertically scrollable page body.
* ``SPACE`` — the shared 4 px spacing grid.

Pure Tk; works with every ttk theme.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

SPACE = 4  # base unit of the spacing grid
GAP = 2 * SPACE
MARGIN = 24  # distance kept between a dialog and the work-area edge
TASKBAR = 48

FLOW_CLASSES = {
    "TButton", "Button", "TCheckbutton", "Checkbutton", "TRadiobutton", "Radiobutton",
    "TMenubutton", "Menubutton", "TLabel", "Label", "TCombobox", "TEntry", "Entry", "TSpinbox",
}


def work_area(widget: tk.Misc) -> tuple[int, int, int, int]:
    """Usable screen area (x, y, w, h); leaves room for the Windows taskbar."""
    try:
        return 0, 0, widget.winfo_screenwidth(), max(480, widget.winfo_screenheight() - TASKBAR)
    except tk.TclError:
        return 0, 0, 1280, 720


def fit_size(widget: tk.Misc, width: int, height: int) -> tuple[int, int]:
    _x, _y, aw, ah = work_area(widget)
    return max(200, min(int(width), aw - MARGIN)), max(160, min(int(height), ah - MARGIN))


def clamp_position(widget: tk.Misc, x: int, y: int, w: int, h: int) -> tuple[int, int]:
    ax, ay, aw, ah = work_area(widget)
    x = min(max(ax, x), ax + max(0, aw - w))
    y = min(max(ay, y), ay + max(0, ah - h))
    return x, y


def clamp_minsize(win: tk.Misc, width: int, height: int) -> tuple[int, int]:
    """``win.minsize`` that never exceeds the work area."""
    _x, _y, aw, ah = work_area(win)
    w, h = min(int(width), aw - MARGIN), min(int(height), ah - MARGIN)
    try:
        win.minsize(max(100, w), max(100, h))
    except tk.TclError:
        pass
    return w, h


def place_dialog(win: tk.Misc, width: int, height: int, parent: tk.Misc | None = None) -> str:
    """Size ``win`` to (width, height) clipped to the work area and centre it on its parent."""
    w, h = fit_size(win, width, height)
    parent = parent if parent is not None else getattr(win, "master", None)
    try:
        top = parent.winfo_toplevel() if parent is not None else None
        if top is not None and top.winfo_ismapped() and top.winfo_width() > 1:
            cx = top.winfo_rootx() + top.winfo_width() // 2
            cy = top.winfo_rooty() + top.winfo_height() // 2
        else:
            ax, ay, aw, ah = work_area(win)
            cx, cy = ax + aw // 2, ay + ah // 2
    except tk.TclError:
        cx, cy = 640, 360
    x, y = clamp_position(win, cx - w // 2, cy - h // 2, w, h)
    geo = f"{w}x{h}+{x}+{y}"
    try:
        win.geometry(geo)
    except tk.TclError:
        pass
    return geo


def keep_on_screen(win: tk.Misc) -> None:
    """Pull an already-shown window back inside the work area (and shrink it if needed)."""
    try:
        mw, mh = win.minsize()
        clamp_minsize(win, mw, mh)
        win.update_idletasks()
        w, h = fit_size(win, win.winfo_width(), win.winfo_height())
        x, y = clamp_position(win, win.winfo_rootx(), win.winfo_rooty(), w, h)
        win.geometry(f"{w}x{h}+{x}+{y}")
    except tk.TclError:
        pass


_BARS: list["FlowBar"] = []
_RTL = [False]


def set_direction(rtl: bool) -> None:
    """Mirror every flow bar (Persian = right-to-left)."""
    _RTL[0] = bool(rtl)
    for bar in list(_BARS):
        try:
            if not bar.frame.winfo_exists():
                _BARS.remove(bar)
                continue
        except tk.TclError:
            _BARS.remove(bar)
            continue
        bar.rtl = _RTL[0]
        bar.reflow(force=True)


def row_style(frame: tk.Misc) -> str:
    """A border-less frame style with the background of ``frame`` (rows inside cards)."""
    try:
        parent = str(frame.cget("style")) or frame.winfo_class()
        style = ttk.Style(frame)
        bg = style.lookup(parent, "background") or style.lookup("TFrame", "background")
        try:  # image-drawn frames (Fluent Card.field) show the page background, not the configured one
            if "Card.field" in str(style.layout(parent)):
                bg = style.lookup("TFrame", "background") or bg
        except tk.TclError:
            pass
        name = f"FlowRow{abs(hash(parent)) % 10_000}.TFrame"
        style.configure(name, background=bg, borderwidth=0, relief="flat", padding=0)
        return name
    except tk.TclError:
        return "TFrame"


def refresh_styles(root: tk.Misc) -> None:
    """Re-derive every flow-row background after a theme change."""
    seen: set[str] = set()
    for bar in list(_BARS):
        try:
            if bar.frame.winfo_exists():
                name = row_style(bar.frame)
                if name not in seen:
                    seen.add(name)
        except tk.TclError:
            continue
    _ = root


def no_flow(frame: tk.Misc) -> tk.Misc:
    """Mark a frame whose children are laid out by its owner (never converted)."""
    frame._aiwb_noflow = True  # type: ignore[attr-defined]
    return frame


class FlowBar:
    """Lays the children of ``frame`` out left-to-right and wraps them onto new rows."""

    def __init__(self, frame: tk.Misc, items: list[tuple[tk.Misc, dict[str, Any]]] | None = None,
                 *, gap: int = GAP, row_gap: int = SPACE, rtl: bool | None = None) -> None:
        self.frame = frame
        self.gap, self.row_gap = gap, row_gap
        self.rtl = _RTL[0] if rtl is None else rtl
        _BARS.append(self)
        self.items: list[tuple[tk.Misc, dict[str, Any]]] = list(items or [])
        self._rows: tuple[tuple[int, ...], ...] = ()
        self._row_frames: list[ttk.Frame] = []
        self._last_width = -1
        frame._aiwb_flow = self  # type: ignore[attr-defined]
        frame.bind("<Configure>", self._on_configure, add="+")
        self.reflow(force=True)

    def add(self, widget: tk.Misc, **opts: Any) -> tk.Misc:
        self.items.append((widget, opts))
        self.reflow(force=True)
        return widget

    def visible_items(self) -> list[tuple[tk.Misc, dict[str, Any]]]:
        return [(w, o) for w, o in self.items if getattr(w, "_aiwb_hidden", False) is False and w.winfo_exists()]

    def _on_configure(self, event: Any) -> None:
        if event.widget is self.frame and event.width != self._last_width:
            self.reflow()

    def _available(self) -> int:
        w = self.frame.winfo_width()
        if w <= 1:
            # not laid out yet: use the parent's width or the request
            try:
                w = self.frame.master.winfo_width()
            except (tk.TclError, AttributeError):
                w = 0
        return w if w > 1 else 10_000

    def _fit_labels(self, width: int) -> None:
        """Wrapped labels in a bar never ask for more than the bar's width."""
        for w, opts in self.items:
            orig = opts.get("wrap")
            if orig:
                try:
                    w.configure(wraplength=max(160, min(orig, width - 2 * self.gap)))
                except tk.TclError:
                    pass

    def rows_for(self, width: int) -> tuple[tuple[int, ...], ...]:
        rows: list[list[int]] = [[]]
        used = 0
        for i, (w, opts) in enumerate(self.items):
            need = w.winfo_reqwidth() + _pad_total(opts.get("padx", 0))
            add = need + (self.gap if rows[-1] else 0)
            if rows[-1] and used + add > width:
                rows.append([])
                used = 0
                add = need
            rows[-1].append(i)
            used += add
        return tuple(tuple(r) for r in rows if r)

    def reflow(self, force: bool = False) -> None:
        try:
            width = self._available()
        except tk.TclError:
            return
        self._last_width = self.frame.winfo_width()
        self._fit_labels(width)
        rows = self.rows_for(width)
        if rows == self._rows and not force:
            return
        self._rows = rows
        bg_style = row_style(self.frame)
        while len(self._row_frames) < len(rows):
            rf = ttk.Frame(self.frame, style=bg_style)
            self._row_frames.append(rf)
        for w, _o in self.items:
            try:
                w.pack_forget()
            except tk.TclError:
                pass
        for i, rf in enumerate(self._row_frames):
            if i < len(rows):
                rf.pack(side="top", fill="x", anchor="e" if self.rtl else "w", pady=(self.row_gap if i else 0, 0))
            else:
                rf.pack_forget()
        side = "right" if self.rtl else "left"
        for r, row in enumerate(rows):
            rf = self._row_frames[r]
            for c, i in enumerate(row):
                w, _opts = self.items[i]
                pad = (0, self.gap if c else 0) if self.rtl else (self.gap if c else 0, 0)
                try:
                    w.pack(in_=rf, side=side, padx=pad)
                    w.lift(rf)
                except tk.TclError:
                    pass


def _pad_pair(p: Any) -> tuple[int, int]:
    if isinstance(p, (tuple, list)):
        vals = [int(float(str(v))) for v in p] or [0]
        return (vals[0], vals[-1])
    try:
        v = int(float(str(p)))
    except ValueError:
        v = 0
    return (v, v)


def _pad_total(p: Any) -> int:
    a, b = _pad_pair(p)
    return a + b


def flow(frame: tk.Misc, **kw: Any) -> FlowBar | None:
    """Convert a frame of packed controls into a :class:`FlowBar` (no-op if unsuitable)."""
    if getattr(frame, "_aiwb_flow", None) is not None:
        return frame._aiwb_flow  # type: ignore[attr-defined]
    if getattr(frame, "_aiwb_noflow", False):
        return None
    try:
        slaves = frame.pack_slaves()
    except tk.TclError:
        return None
    if len(slaves) < 2 or frame.grid_slaves():
        return None
    left: list[tuple[tk.Misc, dict[str, Any]]] = []
    right: list[tuple[tk.Misc, dict[str, Any]]] = []
    for s in slaves:
        try:
            info = s.pack_info()
        except tk.TclError:
            return None
        if s.winfo_class() not in FLOW_CLASSES:
            return None
        wrap = 0
        if s.winfo_class() in ("TLabel", "Label"):
            try:
                wrap = int(float(str(s.cget("wraplength"))))
            except (tk.TclError, ValueError):
                wrap = 0
        expands = str(info.get("expand")) in ("1", "true", "True") or info.get("fill") in ("y", "both")
        if expands and not wrap:
            return None
        side = info.get("side", "top")
        opts = {"wrap": wrap} if wrap else {}
        if side == "left":
            left.append((s, opts))
        elif side == "right":
            right.insert(0, (s, opts))
        else:
            return None
    for s, _o in left + right:
        s.pack_forget()
    return FlowBar(frame, left + right, **kw)


def follow_width(label: tk.Misc, *, margin: int = 8, minimum: int = 160) -> None:
    """Make a wrapped label re-wrap to the width of its container."""
    parent = label.master
    if parent is None:
        return

    def on_cfg(event: Any) -> None:
        if event.widget is not parent:
            return
        try:
            info = label.pack_info() if label.winfo_manager() == "pack" else {}
            side = info.get("side", "top")
            if side in ("left", "right"):
                return
            label.configure(wraplength=max(minimum, event.width - margin))
        except tk.TclError:
            pass

    parent.bind("<Configure>", on_cfg, add="+")


def auto_flow(root: tk.Misc) -> int:
    """Apply :func:`flow` to every control row and :func:`follow_width` to wrapped labels."""
    n = 0
    stack: list[tk.Misc] = [root]
    while stack:
        w = stack.pop()
        try:
            children = w.winfo_children()
            cls = w.winfo_class()
        except tk.TclError:
            continue
        if isinstance(w, tk.Toplevel) and w is not root:
            continue
        if cls in ("TFrame", "Frame", "TLabelframe", "Labelframe") and flow(w) is not None:
            n += 1
        if cls in ("TLabel", "Label"):
            try:
                if int(float(str(w.cget("wraplength")))) > 0 and not getattr(w, "_aiwb_follow", False):
                    follow_width(w)
                    w._aiwb_follow = True  # type: ignore[attr-defined]
            except (tk.TclError, ValueError):
                pass
        stack.extend(children)
    return n


def _on_dialog_map(event: Any) -> None:
    win = event.widget
    if not isinstance(win, tk.Toplevel) or getattr(win, "_aiwb_placed", False):
        return
    try:
        if win.winfo_class() == "ComboboxPopdown" or win.overrideredirect():
            return
    except tk.TclError:
        return
    win._aiwb_placed = True  # type: ignore[attr-defined]
    auto_flow(win)
    keep_on_screen(win)


def install(root: tk.Misc) -> None:
    """Every dialog, the first time it is shown: fit to the work area and wrap its toolbars."""
    root.bind_class("Toplevel", "<Map>", _on_dialog_map, add="+")


class ScrollPage(ttk.Frame):
    """A frame with a vertically scrollable ``body``; the body always matches the visible width."""

    def __init__(self, master: tk.Misc, **kw: Any) -> None:
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.body.bind("<Configure>", lambda _e: self._sync())
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfigure(self._win, width=e.width), self._sync()))

    def _sync(self) -> None:
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))
            self.canvas.configure(background=ttk.Style(self).lookup("TFrame", "background") or "")
        except tk.TclError:
            pass


def _rect(w: tk.Misc) -> tuple[int, int, int, int]:
    x, y = w.winfo_rootx(), w.winfo_rooty()
    return x, y, x + w.winfo_width(), y + w.winfo_height()


def outside_window(top: tk.Misc, classes: tuple[str, ...] = ("TButton", "Button", "TCheckbutton", "TRadiobutton", "TMenubutton")) -> list[str]:
    """Mapped controls that are cut off: squeezed below their requested width, or not fully
    visible inside every ancestor up to ``top``. Content of scrollable canvases is skipped."""
    top.update_idletasks()
    bad: list[str] = []
    stack: list[tuple[tk.Misc, tuple[int, int, int, int]]] = [(c, _rect(top)) for c in top.winfo_children()]
    while stack:
        w, clip = stack.pop()
        try:
            if isinstance(w, tk.Toplevel) or w.winfo_class() in ("Canvas", "Menu", "Text", "Treeview", "Listbox") or not w.winfo_ismapped():
                continue
            r = _rect(w)
            if w.winfo_class() in classes:
                squeezed = w.winfo_width() + 2 < w.winfo_reqwidth()
                outside = r[0] < clip[0] - 1 or r[1] < clip[1] - 1 or r[2] > clip[2] + 1 or r[3] > clip[3] + 1
                if squeezed or outside:
                    label = w.cget("text") if "text" in w.keys() else ""
                    bad.append(f"{label or w} [{'squeezed' if squeezed else 'clipped'}]")
                continue
            inner = (max(clip[0], r[0]), max(clip[1], r[1]), min(clip[2], r[2]), min(clip[3], r[3]))
            stack.extend((c, inner) for c in w.winfo_children())
        except tk.TclError:
            continue
    return bad
