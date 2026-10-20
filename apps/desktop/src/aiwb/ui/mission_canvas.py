"""Mission Map canvas (roadmap 5.2.0): draws :func:`mission_model.build` the way the owner's reference image does.

PROJECT START capsule → golden source node → curved anti-aliased branches → green numbered hexagons (one per AI) →
a horizontal lane per AI with one circle per task in its version's dashed column → a chevron at the lane end.
Every soft shape is a cached PNG from :mod:`assets`; straight hairlines are plain canvas lines (crisp anyway).

Hover: halo + tooltip. Click: ``on_select(task_id)``. Right-click: ``on_menu(task_id, x_root, y_root)``
(the menu itself is 5.4.0). Drag / wheel / arrow keys scroll. Drawing never touches project data.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from . import mission_model
from .assets import Assets
from .tokens5 import font5, palette5

STATE_SPRITE = {"done": "task_done", "active": "task_active", "blocked": "task_blocked",
                "attention": "task_attention", "idle": "task_idle"}
STATE_TEXT = {"done": "Done", "active": "In progress", "blocked": "Blocked", "attention": "Needs a decision",
              "idle": "Waiting"}


class MissionCanvas(tk.Canvas):
    def __init__(self, master: tk.Misc, assets: Assets, *, on_select: Callable[[str], Any] | None = None,
                 on_menu: Callable[[str, int, int], Any] | None = None, **kw: Any) -> None:
        super().__init__(master, highlightthickness=0, bd=0, **kw)
        self._aiwb_keep_colours = True
        self.assets = assets
        self.on_select, self.on_menu = on_select, on_menu
        self.model: dict[str, Any] = mission_model.build(None)
        self.geo: dict[str, Any] = {}
        self.node_items: dict[int, str] = {}      # canvas id → task id
        self.node_ids: dict[str, int] = {}        # task id → canvas id
        self.hovered = ""
        self.selected = ""
        self._halo: int | None = None
        self._tip: list[int] = []
        self._drag: tuple[int, int] | None = None
        self.bind("<Configure>", lambda _e: self._fit_scrollregion())
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._unhover())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag_to)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Button-3>", self._context)
        self.bind("<MouseWheel>", lambda e: self.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.bind("<Shift-MouseWheel>", lambda e: self.xview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.bind("<Button-4>", lambda _e: self.yview_scroll(-1, "units"))
        self.bind("<Button-5>", lambda _e: self.yview_scroll(1, "units"))
        for key, fn in (("<Left>", lambda _e: self.xview_scroll(-3, "units")),
                        ("<Right>", lambda _e: self.xview_scroll(3, "units")),
                        ("<Up>", lambda _e: self.yview_scroll(-3, "units")),
                        ("<Down>", lambda _e: self.yview_scroll(3, "units"))):
            self.bind(key, fn)
        self.configure(xscrollincrement=20, yscrollincrement=20)
        self.redraw()

    # -- data
    def set_state(self, state: dict[str, Any] | None) -> dict[str, Any]:
        self.model = mission_model.build(state)
        self.redraw()
        return self.model

    def set_theme(self, theme: str) -> None:
        self.assets.set_theme(theme)
        self.redraw()

    # -- drawing
    def redraw(self) -> None:
        p = palette5(self.assets.theme)
        s = self.assets.scale
        self.delete("all")
        self.node_items.clear()
        self.node_ids.clear()
        self._halo = None
        self._tip = []
        self.configure(background=p["field"])
        m = self.model
        if m["empty"]:
            self.create_text(24 * s, 40 * s, anchor="nw", fill=p["text_dim"], font=font5("title", s),
                             text="No plan yet", tags=("empty",))
            self.create_text(24 * s, 66 * s, anchor="nw", fill=p["text_faint"], font=font5("body", s),
                             text="Open a project and plan it with your project-manager AI in the Workbench. "
                                  "Each AI then gets its own lane here.", tags=("empty",))
            self._fit_scrollregion()
            return
        g = self.geo = mission_model.layout(m, s)
        top, bottom = g["top"] - 26 * s, g["height"] - 12 * s
        # version columns: dashed rails and mono labels
        for i, col in enumerate(m["columns"]):
            x = g["col_x"][i]
            done = col.get("status") in ("released", "accepted")
            self.create_line(x, top + 16 * s, x, bottom, fill=p["version"] if not done else p["go"],
                             dash=(max(2, round(4 * s)), max(2, round(5 * s))), width=max(1, round(s)),
                             tags=("column",))
            self.create_text(x, top, text=col["label"], fill=p["version"] if not done else p["go"],
                             font=font5("mono", s), tags=("column_label",))
        # lanes
        for i, lane in enumerate(m["lanes"]):
            y = g["lane_y"][i]
            x0 = g["hex_x"]
            self.create_line(x0, y, g["end_x"] - 12 * s, y, fill=p["idle_ring"] if lane["live"] else p["line"],
                             width=max(1, round(1.3 * s)), tags=("lane",))
            self.create_image(g["end_x"], y, image=self.assets.icon("chevron_right", 16, role="text_faint"),
                              tags=("chevron",))
        # branches from the source to every hexagon
        sx, sy = g["source"]
        for i, lane in enumerate(m["lanes"]):
            y = g["lane_y"][i]
            w = max(2, int(g["hex_x"] - sx))
            y0, y1 = min(sy, y), max(sy, y)
            h = max(4, int(y1 - y0 + 8 * s))
            img = self.assets.sprite("branch", w=w, h=h, y0=round(sy - y0 + 4 * s, 1), y1=round(y - y0 + 4 * s, 1),
                                     lit=lane["live"], role="text_dim" if lane["live"] else "text_faint")
            self.create_image(sx, y0 - 4 * s, image=img, anchor="nw", tags=("branch",))
        # capsule + source
        cx, cy, cw = g["capsule"]
        cap = self.assets.sprite("capsule", w=round(cw / s))
        self.create_image(cx + cw / 2, cy, image=cap, tags=("capsule",))
        self.create_text(cx + cw / 2, cy, text="PROJECT START", fill=p["go_hi"], font=font5("capsule", s),
                         tags=("capsule",))
        self.create_line(cx + cw, cy, sx, cy, fill=p["source"], width=max(1, round(1.4 * s)), tags=("capsule",))
        self.create_image(sx, sy, image=self.assets.sprite("source"), tags=("source",))
        # hexagons
        for i, lane in enumerate(m["lanes"]):
            y = g["lane_y"][i]
            self.create_image(g["hex_x"], y, image=self.assets.sprite("hex"), tags=("hex", f"lane:{lane['agent_id']}"))
            self.create_text(g["hex_x"], y, text=str(lane["number"]), fill=p["go_hi"], font=font5("capsule", s),
                             tags=("hex", f"lane:{lane['agent_id']}"))
        # task circles
        for lane in m["lanes"]:
            for nd in lane["nodes"]:
                x, y = g["nodes"][nd["task_id"]]
                sprite = STATE_SPRITE[nd["state"]] if nd["task_id"] != self.selected else "task_selected"
                cid = self.create_image(x, y, image=self.assets.sprite(sprite), tags=("node", nd["task_id"]))
                self.node_items[cid] = nd["task_id"]
                self.node_ids[nd["task_id"]] = cid
        self._fit_scrollregion()

    def _fit_scrollregion(self) -> None:
        bbox = self.bbox("all") or (0, 0, 1, 1)
        w = max(bbox[2] + 20, self.winfo_width())
        h = max(bbox[3] + 20, self.winfo_height())
        self.configure(scrollregion=(0, 0, w, h))

    # -- lookup
    def node(self, task_id: str) -> dict[str, Any] | None:
        for lane in self.model["lanes"]:
            for nd in lane["nodes"]:
                if nd["task_id"] == task_id:
                    return {**nd, "agent_id": lane["agent_id"], "lane_name": lane["name"]}
        return None

    def task_at(self, x: int, y: int) -> str:
        """Task under widget coordinates (x, y), within the circle's radius + a small margin."""
        cx, cy = self.canvasx(x), self.canvasy(y)
        r = (11 + 4) * self.assets.scale
        best, dist = "", r * r
        for tid, (nx, ny) in (self.geo.get("nodes") or {}).items():
            d = (nx - cx) ** 2 + (ny - cy) ** 2
            if d <= dist:
                best, dist = tid, d
        return best

    # -- interaction
    def _motion(self, e: Any) -> None:
        tid = self.task_at(e.x, e.y)
        if tid != self.hovered:
            self._unhover()
            if tid:
                self._hover(tid)

    def _hover(self, tid: str) -> None:
        p = palette5(self.assets.theme)
        s = self.assets.scale
        self.hovered = tid
        self.configure(cursor="hand2")
        x, y = self.geo["nodes"][tid]
        self._halo = self.create_image(x, y, image=self.assets.sprite("task_hover"), tags=("halo",))
        nd = self.node(tid) or {}
        if nd.get("state") not in ("active", "idle"):
            self.tag_raise(self.node_ids[tid])
        text = f"{nd.get('title', tid)}\n{tid} · {nd.get('lane_name', '')} · {STATE_TEXT.get(nd.get('state', ''), '')}"
        t = self.create_text(x + 18 * s, y - 30 * s, text=text, anchor="sw", fill=p["text"], font=font5("small", s),
                             tags=("tip",))
        bb = self.bbox(t)
        pad = 7 * s
        bg = self.create_rectangle(bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad, fill=p["menu"],
                                   outline=p["menu_border"], tags=("tip",))
        self.tag_raise(t, bg)
        self._tip = [bg, t]

    def _unhover(self) -> None:
        if self._halo is not None:
            self.delete(self._halo)
            self._halo = None
        for i in self._tip:
            self.delete(i)
        self._tip = []
        self.hovered = ""
        self.configure(cursor="")

    def _press(self, e: Any) -> None:
        self.focus_set()
        self._drag = (e.x, e.y)
        self.scan_mark(e.x, e.y)

    def _drag_to(self, e: Any) -> None:
        if self._drag is not None:
            self.scan_dragto(e.x, e.y, gain=1)

    def _release(self, e: Any) -> None:
        start, self._drag = self._drag, None
        if start is not None and abs(e.x - start[0]) + abs(e.y - start[1]) > 4:
            return  # it was a pan
        tid = self.task_at(e.x, e.y)
        if tid:
            self.select(tid)

    def select(self, tid: str) -> None:
        self.selected = tid
        self.redraw()
        if self.on_select is not None:
            self.on_select(tid)

    def _context(self, e: Any) -> None:
        tid = self.task_at(e.x, e.y)
        if tid and self.on_menu is not None:
            self.on_menu(tid, e.x_root, e.y_root)
