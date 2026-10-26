"""Visual timeline (roadmap 3.6.0).

A horizontal time axis with one lane per AI (plus "project"); every ledger event is a circle whose size
shows its importance (minor / normal / major / critical); every version is a vertical line — dashed while
it is only proposed/local/tagged, solid once released. Zoom (wheel / +/-), pan (drag / arrows), tooltip on
hover, click → ``on_select(event_id)`` (the Workbench opens it in the Inspector).

:func:`build_model` is pure (no Tk) so the data mapping is unit-tested; :class:`TimelineCanvas` only draws.
English only (product language policy 2026-10-19).
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from typing import Any, Callable

IMPORTANCE = ("minor", "normal", "major", "critical")
RADIUS = {"minor": 3, "normal": 5, "major": 8, "critical": 11}

_CRITICAL = {"release_published", "charter_accepted"}
_MAJOR = {"milestone_accepted", "version_created", "proposal_reviewed", "decision_accepted", "decision_rejected",
          "handoff_accepted", "handoff_rejected", "milestone_created", "version_proposed", "version_withdrawn"}
_NORMAL_PREFIX = ("task_", "handoff_", "evidence_", "decision_", "attempt_", "user_confirmed_sent", "prompt_")

LANE_H = 34
TOP = 26
LEFT = 130
RIGHT = 20


def importance(rec: dict[str, Any]) -> str:
    """Importance of one ledger record (explicit ``payload.importance`` wins)."""
    explicit = str((rec.get("payload") or {}).get("importance", ""))
    if explicit in IMPORTANCE:
        return explicit
    et = str(rec.get("event_type", ""))
    after = rec.get("after") or {}
    if et in _CRITICAL or (et == "task_status" and after.get("new") == "done"):
        return "critical"
    if et in _MAJOR or (et == "task_status" and after.get("new") in ("blocked", "needs_decision")):
        return "major"
    if et.startswith(_NORMAL_PREFIX):
        return "normal"
    return "minor"


def _ts(s: str) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def build_model(records: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    """Map ledger records + versions to drawable items (pure).

    Events without a timestamp (legacy imports) take the time of the previous event so order is kept.
    """
    owner = {tid: t.get("owner_agent_id", "") for tid, t in state.get("tasks", {}).items()}
    events: list[dict[str, Any]] = []
    last: float | None = None
    undated: list[dict[str, Any]] = []
    for rec in records:
        refs = rec.get("refs") or {}
        lane = refs.get("agent_id") or refs.get("to_agent_id") or owner.get(refs.get("task_id", ""), "") or "project"
        t = _ts(rec.get("timestamp_utc", ""))
        ev = {"id": rec.get("event_id", ""), "type": rec.get("event_type", ""), "lane": lane, "t": t,
              "importance": importance(rec), "dated": t is not None,
              "label": f"{rec.get('event_type', '')} {refs.get('task_id') or refs.get('version_id') or refs.get('milestone_id') or ''}".strip(),
              "when": rec.get("timestamp_utc") or "time unknown (legacy)"}
        if t is None:
            if last is None:
                undated.append(ev)
            else:
                ev["t"] = last
        else:
            last = t
            for u in undated:
                u["t"] = t
            undated = []
        events.append(ev)
    for u in undated:
        u["t"] = 0.0
    versions = []
    for v in sorted(state.get("versions", {}).values(), key=lambda v: v["version_id"]):
        if v["status"] == "withdrawn":
            continue
        released = next((h["at"] for h in v.get("history", []) if h.get("to") == "released"), "")
        t = _ts(released) if released else _ts(v.get("created_at", ""))
        if t is None:
            continue
        versions.append({"id": v["version_id"], "label": v["label"], "t": t, "released": bool(released),
                         "status": v["status"]})
    lanes = ["project"] + sorted({e["lane"] for e in events if e["lane"] != "project"})
    if not any(e["lane"] == "project" for e in events) and len(lanes) > 1:
        lanes = lanes[1:]
    times = [e["t"] for e in events] + [v["t"] for v in versions]
    t0, t1 = (min(times), max(times)) if times else (0.0, 1.0)
    if t1 <= t0:
        t1 = t0 + 1.0
    # 5.13.0 (owner audit C4): a lane is titled with the AI's name ("Core developer"), never its id; "project" → "Project"
    names = {aid: str(a.get("name") or aid) for aid, a in (state.get("agents") or {}).items()}
    lane_names = {ln: ("Project" if ln == "project" else names.get(ln, ln)) for ln in lanes}
    return {"events": events, "versions": versions, "lanes": lanes, "lane_names": lane_names, "t0": t0, "t1": t1}


def fit_label(text: str, limit: int = 18) -> str:
    """A lane title that fits the label column (LEFT px): long names end with "…" instead of running under the axis."""
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def when_label(t: float) -> str:
    """'26 Oct 14:05' for an axis end ('' for the 0.0 placeholder of a model without dated events)."""
    if t <= 0:
        return ""
    try:
        return datetime.fromtimestamp(t).strftime("%d %b %H:%M")
    except (OverflowError, OSError, ValueError):
        return ""


class TimelineCanvas(tk.Canvas):
    """Draws a :func:`build_model` result. ``palette`` uses the Workbench theme tokens."""

    def __init__(self, master: tk.Misc, *, palette: dict[str, str] | None = None,
                 on_select: Callable[[str], Any] | None = None, **kw: Any) -> None:
        p = palette or {}
        super().__init__(master, background=p.get("surface", "#ffffff"), highlightthickness=0, **kw)
        self.p = {"text": p.get("text", "#1c1c1c"), "muted": p.get("muted", "#5c5c5c"),
                  "grid": p.get("divider", "#e5e5e5"), "accent": p.get("accent", "#005fb8"),
                  "success": p.get("success", "#0e700e"), "warning": p.get("warning", "#8a5300"),
                  "danger": p.get("danger", "#c42b1c"), "surface": p.get("surface", "#ffffff")}
        self.on_select = on_select
        self.model: dict[str, Any] = {"events": [], "versions": [], "lanes": [], "t0": 0.0, "t1": 1.0}
        self.zoom = 1.0
        self.offset = 0.0           # pixels the content is shifted left
        self.items: dict[int, dict[str, Any]] = {}   # canvas id → event / version
        self.selected = ""
        self._tip: int | None = None
        self._tip_bg: int | None = None
        self._drag: float | None = None
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda e: self.zoom_at(1.25, e.x))
        self.bind("<Button-5>", lambda e: self.zoom_at(0.8, e.x))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda _e: self._hide_tip())
        for key, fn in (("<plus>", lambda _e: self.zoom_at(1.25)), ("<minus>", lambda _e: self.zoom_at(0.8)),
                        ("<Left>", lambda _e: self.pan(-60)), ("<Right>", lambda _e: self.pan(60))):
            self.bind(key, fn)

    # -- geometry
    def width_px(self) -> int:
        return max(int(self.winfo_width()), 200)

    def x_of(self, t: float) -> float:
        m = self.model
        span = max(self.width_px() - LEFT - RIGHT, 50) * self.zoom
        return LEFT + (t - m["t0"]) / (m["t1"] - m["t0"]) * span - self.offset

    def t_at(self, x: float) -> float:
        """The time under the x pixel (inverse of :meth:`x_of`)."""
        m = self.model
        span = max(self.width_px() - LEFT - RIGHT, 50) * self.zoom
        return m["t0"] + (x + self.offset - LEFT) / span * (m["t1"] - m["t0"])

    def _fit_px(self, text: str, room: int = LEFT - 22) -> str:
        """Trim ``text`` (ending in "…") until it is at most ``room`` pixels wide in the lane font."""
        try:
            from tkinter import font as tkfont
            f = tkfont.Font(root=self, family="Segoe UI", size=9)
        except tk.TclError:
            return text
        while len(text) > 2 and f.measure(text) > room:
            text = text.rstrip("…")[:-1].rstrip() + "…"
        return text

    def y_of(self, lane: str) -> float:
        lanes = self.model["lanes"]
        i = lanes.index(lane) if lane in lanes else 0
        return TOP + LANE_H * i + LANE_H / 2

    # -- data
    def set_model(self, model: dict[str, Any]) -> None:
        self.model = model
        self.redraw()

    def zoom_at(self, factor: float, x: float | None = None) -> None:
        x = LEFT if x is None else x
        old = self.zoom
        self.zoom = min(max(self.zoom * factor, 1.0), 400.0)
        # keep the point under the cursor in place
        self.offset = max((self.offset + x - LEFT) * self.zoom / old - (x - LEFT), 0.0)
        self.redraw()

    def pan(self, dx: float) -> None:
        span = max(self.width_px() - LEFT - RIGHT, 50) * self.zoom
        self.offset = min(max(self.offset + dx, 0.0), max(span - (self.width_px() - LEFT - RIGHT), 0.0))
        self.redraw()

    # -- drawing
    def redraw(self) -> None:
        self.delete("all")
        self.items.clear()
        self._tip = self._tip_bg = None
        m, p = self.model, self.p
        w = self.width_px()
        h = TOP + LANE_H * max(len(m["lanes"]), 1) + 18  # + the date line under the lanes
        self.configure(scrollregion=(0, 0, w, h))
        names = m.get("lane_names") or {}
        for lane in m["lanes"]:
            y = self.y_of(lane)
            self.create_line(LEFT, y, w - RIGHT, y, fill=p["grid"])
            # 5.13.0 (owner audit C4): the AI's name, cut with "…" to fit the label column (it was clipped by the axis)
            self.create_text(8, y, text=self._fit_px(fit_label(names.get(lane, lane))), anchor="w", fill=p["muted"],
                             font=("Segoe UI", 9))
        if m["events"] or m["versions"]:  # the two ends of the shown span, so the axis says when
            for t, anchor in ((self.t_at(LEFT), "sw"), (self.t_at(w - RIGHT), "se")):
                self.create_text(LEFT if anchor == "sw" else w - RIGHT, h - 1, text=when_label(t), anchor=anchor,
                                 fill=p["muted"], font=("Segoe UI", 8))
        for v in m["versions"]:
            x = self.x_of(v["t"])
            if x < LEFT or x > w - RIGHT:
                continue
            cid = self.create_line(x, TOP - 2, x, h - 14, fill=p["success"] if v["released"] else p["accent"],
                                   width=2, dash=() if v["released"] else (5, 4), tags=("version",))
            self.items[cid] = {"kind": "version", **v}
            # the label sits above the lanes, left of the line near the right edge (it overlapped the dot before)
            right = x > w - RIGHT - 80
            self.create_text(x - 4 if right else x + 4, TOP - 12, text="v" + str(v["label"]).lstrip("vV"),
                             anchor="e" if right else "w", fill=p["text"], font=("Segoe UI", 8, "bold"))
        colour = {"critical": p["danger"], "major": p["warning"], "normal": p["accent"], "minor": p["muted"]}
        for ev in m["events"]:
            x = self.x_of(ev["t"])
            if x < LEFT - 12 or x > w - RIGHT + 12:
                continue
            r = RADIUS[ev["importance"]]
            y = self.y_of(ev["lane"])
            cid = self.create_oval(x - r, y - r, x + r, y + r, fill=colour[ev["importance"]],
                                   outline=p["text"] if ev["id"] == self.selected else p["surface"],
                                   width=2 if ev["id"] == self.selected else 1, tags=("event",))
            self.items[cid] = {"kind": "event", **ev}

    # -- interaction
    def item_at(self, x: float, y: float) -> dict[str, Any] | None:
        for cid in reversed(self.find_overlapping(x - 2, y - 2, x + 2, y + 2)):
            if cid in self.items:
                return self.items[cid]
        return None

    def _wheel(self, e: Any) -> None:
        self.zoom_at(1.25 if e.delta > 0 else 0.8, e.x)

    def _press(self, e: Any) -> None:
        self.focus_set()
        self._drag = e.x
        self._moved = False

    def _motion(self, e: Any) -> None:
        if self._drag is not None and abs(e.x - self._drag) > 2:
            self._moved = True
            self.pan(self._drag - e.x)
            self._drag = e.x

    def _release(self, e: Any) -> None:
        moved = getattr(self, "_moved", False)
        self._drag = None
        if not moved:
            self.click(e.x, e.y)

    def click(self, x: float, y: float) -> dict[str, Any] | None:
        it = self.item_at(x, y)
        if it and it["kind"] == "event":
            self.selected = it["id"]
            self.redraw()
            if self.on_select:
                self.on_select(it["id"])
        return it

    def tooltip_text(self, it: dict[str, Any]) -> str:
        if it["kind"] == "version":
            return f"Version {it['label']} — {'released' if it['released'] else it['status'] + ' (planned)'}"
        return f"{it['label']} · {it['importance']} · {it['lane']} · {it['when']}"

    def _hover(self, e: Any) -> None:
        it = self.item_at(e.x, e.y)
        if not it:
            self._hide_tip()
            return
        self._hide_tip()
        x = min(e.x + 12, self.width_px() - 260)
        self._tip = self.create_text(x + 4, e.y + 14, text=self.tooltip_text(it), anchor="nw", fill=self.p["text"],
                                     font=("Segoe UI", 9))
        bb = self.bbox(self._tip)
        self._tip_bg = self.create_rectangle(bb[0] - 4, bb[1] - 2, bb[2] + 4, bb[3] + 2, fill=self.p["surface"],
                                             outline=self.p["muted"])
        self.tag_raise(self._tip)

    def _hide_tip(self) -> None:
        for cid in (self._tip, self._tip_bg):
            if cid:
                self.delete(cid)
        self._tip = self._tip_bg = None
