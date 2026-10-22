"""Projects page cards (roadmap 5.7.0): one card per project in the local library.

Home shows only the *active* project (its Mission Map and next step); the Projects page owns the library — every
registered project as a card (name, state, description, last opened, folder), then the Workbench of the open one.

:func:`rows` is pure (settings records in, card rows out) so the mapping is unit-tested; :class:`ProjectCards` only
draws them on a Tk Canvas with the 5.x tokens. A click selects a card (``on_select(path)``); a double-click opens it
(``on_open(path)``). Drawing never touches project data.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any, Callable

from .assets import Assets
from .tokens5 import font5, palette5

STATE_ROLE = {"Active": "active", "Ready": "go", "Missing": "danger"}


def _short(path: str, limit: int = 38) -> str:
    return path if len(path) <= limit else "…" + path[-(limit - 1):]


def rows(records: list[Any], active: str | Path | None, query: str = "",
         manifest: Callable[[Path], dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """One row per valid project record (active first, then most recently opened), filtered by ``query``."""
    act = str(Path(active).resolve()).casefold() if active else ""
    q = query.strip().casefold()
    out: list[dict[str, Any]] = []
    for rec in records if isinstance(records, list) else []:
        if not isinstance(rec, dict) or not isinstance(rec.get("path"), str):
            continue
        path = Path(rec["path"])
        exists = path.is_dir()
        man = (manifest(path) if (manifest and exists) else {}) or {}
        name = str(man.get("name") or rec.get("name") or path.name or "Unnamed project")
        desc = str(man.get("description") or rec.get("description") or "")
        try:
            is_active = bool(act) and str(path.resolve()).casefold() == act
        except OSError:
            is_active = False
        state = "Active" if is_active else ("Ready" if exists else "Missing")
        last = str(rec.get("last_opened", ""))[:16].replace("T", " ")
        if q and q not in " ".join((name, desc, str(path))).casefold():
            continue
        out.append({"path": str(path), "name": name, "description": desc, "state": state, "last_opened": last})
    # most recent first after the active one (stable: ties keep the library order)
    active_rows = [r for r in out if r["state"] == "Active"]
    rest = sorted((r for r in out if r["state"] != "Active"), key=lambda r: r["last_opened"], reverse=True)
    return active_rows + rest


class ProjectCards(tk.Canvas):
    """The project library as one horizontal row of cards (wheel / Shift+wheel / drag scroll it sideways)."""

    CARD_W, CARD_H, GAP = 268, 74, 10

    def __init__(self, master: tk.Misc, assets: Assets, *, on_select: Callable[[str], Any] | None = None,
                 on_open: Callable[[str], Any] | None = None, **kw: Any) -> None:
        super().__init__(master, highlightthickness=0, bd=0, height=self.CARD_H + 2 * self.GAP, **kw)
        self._aiwb_keep_colours = True
        self.assets = assets
        self.on_select = on_select
        self.on_open = on_open
        self.rows: list[dict[str, Any]] = []
        self.selected = ""
        self.card_of: dict[int, str] = {}
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<Double-Button-1>", self._double)
        self.bind("<MouseWheel>", lambda e: self.scroll(-1 if e.delta > 0 else 1))
        self.bind("<Shift-MouseWheel>", lambda e: self.scroll(-1 if e.delta > 0 else 1))
        self.bind("<Button-4>", lambda _e: self.scroll(-1))
        self.bind("<Button-5>", lambda _e: self.scroll(1))

    def scroll(self, step: int) -> None:
        self.xview_scroll(step * (self.CARD_W + self.GAP) // 4, "units")

    def set_rows(self, rows_: list[dict[str, Any]], selected: str = "") -> None:
        self.rows = rows_
        paths = {r["path"] for r in rows_}
        if selected in paths:
            self.selected = selected
        elif self.selected not in paths:
            self.selected = rows_[0]["path"] if rows_ else ""
        self.draw()

    def select(self, path: str) -> None:
        self.selected = path
        self.draw()
        if self.on_select:
            self.on_select(path)

    def path_at(self, x: float, y: float) -> str:
        for cid in self.find_overlapping(x - 1, y - 1, x + 1, y + 1):
            p = self.card_of.get(cid)
            if p:
                return p
        return ""

    def _press(self, e: tk.Event) -> None:
        p = self.path_at(e.x, e.y)
        if p:
            self.select(p)

    def _double(self, e: tk.Event) -> None:
        p = self.path_at(e.x, e.y)
        if p and self.on_open:
            self.on_open(p)

    def draw(self) -> None:
        p = palette5(self.assets.theme)
        self.delete("all")
        self.card_of = {}
        self.configure(background=p["panel"])
        if not self.rows:
            self.create_text(self.GAP, self.GAP + 10, anchor="w", fill=p["text_dim"], font=font5("body"),
                             text="No projects yet — create one with + New project, or open a folder.")
            self.configure(height=44, scrollregion=(0, 0, 0, 0))
            return
        cw, ch, gap = self.CARD_W, self.CARD_H, self.GAP
        self.configure(xscrollincrement=1)
        for i, r in enumerate(self.rows):
            x0 = gap + i * (cw + gap)
            y0 = gap
            sel = r["path"] == self.selected
            card = self.create_rectangle(x0, y0, x0 + cw, y0 + ch, fill=p["raised"],
                                         outline=p["active"] if sel else p["line"], width=2 if sel else 1)
            self.card_of[card] = r["path"]
            col = p[STATE_ROLE[r["state"]]]
            items = [self.create_image(x0 + 22, y0 + 24, image=self.assets.icon("projects", 20, color=col)),
                     self.create_text(x0 + 42, y0 + 18, anchor="w", text=r["name"], fill=p["text"],
                                      font=font5("title")),
                     self.create_oval(x0 + cw - 74, y0 + 14, x0 + cw - 66, y0 + 22, fill=col, outline=col),
                     self.create_text(x0 + cw - 60, y0 + 18, anchor="w", text=r["state"], fill=col,
                                      font=font5("small")),
                     self.create_text(x0 + 42, y0 + 36, anchor="w", fill=p["text_dim"], font=font5("small"),
                                      text=(r["description"] or _short(r["path"]))[:44]),
                     self.create_text(x0 + 14, y0 + 58, anchor="w", fill=p["text_faint"], font=font5("caption"),
                                      text=f"Last opened {r['last_opened'] or '—'}")]
            for it in items:
                self.card_of[it] = r["path"]
        width = gap + len(self.rows) * (cw + gap)
        self.configure(scrollregion=(0, 0, width, ch + 2 * gap))
        if int(float(self.cget("height"))) != ch + 2 * gap:
            self.configure(height=ch + 2 * gap)
