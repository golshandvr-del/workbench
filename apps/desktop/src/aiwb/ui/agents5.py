"""Agents hub cards (roadmap 5.6.0): one card per AI — numbered hexagon, name, role, live state, current task, load.

:func:`cards` is pure (state in, rows out) and numbers the AIs exactly like the Mission Map lanes, so "AI 3" on
the Agents page is lane 3 on Home. :class:`AgentCards` draws the rows on a Tk Canvas with the cached sprites of
:mod:`assets`; a click selects a card (``on_select(agent_id)``). Drawing never touches project data.
"""
from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from . import mission_model
from .assets import Assets
from .tokens5 import font5, palette5

ALERT_TEXT = {"idle": "Idle", "stuck": "Stuck", "overloaded": "Overloaded", "overlap": "Scope overlap"}
ROLE_TEXT = {"project_manager": "Project manager", "architect": "Architect", "implementer": "Implementer",
             "reviewer": "Reviewer", "researcher": "Researcher"}


def cards(state: dict[str, Any] | None) -> list[dict[str, Any]]:
    """One row per enabled AI: hub stats + Mission Map lane number + its alerts (most urgent kind first)."""
    if not state:
        return []
    from aiwb.v2 import agent_hub
    lanes = {ln["agent_id"]: ln["number"] for ln in mission_model.build(state)["lanes"]}
    found = agent_hub.alerts(state)
    rows = []
    nxt = max(lanes.values(), default=0)
    for r in agent_hub.agent_stats(state):
        if r["agent_id"] not in lanes:
            nxt += 1
            lanes[r["agent_id"]] = nxt
        mine = [a for a in found if r["agent_id"] in (a["agent_id"], a.get("other_agent_id"))]
        rows.append({**r, "number": lanes[r["agent_id"]], "alerts": [a["kind"] for a in mine],
                     "alert_text": [a["text"] for a in mine],
                     "role_text": ROLE_TEXT.get(r["role"], r["role"].replace("_", " ").capitalize())})
    return sorted(rows, key=lambda x: x["number"])


def state_of(row: dict[str, Any]) -> str:
    """The card's live state word: Stuck / Overloaded / Working / Idle / Free."""
    if "stuck" in row["alerts"]:
        return "Stuck"
    if "overloaded" in row["alerts"]:
        return "Overloaded"
    if row["current_task_id"]:
        return "Working"
    return "Idle" if "idle" in row["alerts"] else "Free"


def stats_line(row: dict[str, Any]) -> str:
    avg = "—" if row["avg_delivery_hours"] is None else f"{row['avg_delivery_hours']:g} h"
    return f"{row['done']} done · {row['open']} open · rework {round(row['rework_rate'] * 100)}% · avg {avg}"


def summary(rows: list[dict[str, Any]]) -> str:
    """Plain-text team summary (for the clipboard and the screen reader)."""
    return "\n".join(f"{r['number']}. {r['name']} · {r['role_text']} · {state_of(r)} · {stats_line(r)}"
                     + (f" · now {r['current_task_id']}" if r["current_task_id"] else "") for r in rows)


class AgentCards(tk.Canvas):
    """The team as a wrapping grid of cards."""

    CARD_W, CARD_H, GAP = 268, 112, 12

    def __init__(self, master: tk.Misc, assets: Assets, *, on_select: Callable[[str], Any] | None = None,
                 **kw: Any) -> None:
        super().__init__(master, highlightthickness=0, bd=0, height=self.CARD_H + 2 * self.GAP, **kw)
        self._aiwb_keep_colours = True
        self.assets = assets
        self.on_select = on_select
        self.rows: list[dict[str, Any]] = []
        self.selected = ""
        self.card_of: dict[int, str] = {}
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonPress-1>", self._press)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        if self.selected not in {r["agent_id"] for r in rows}:
            self.selected = rows[0]["agent_id"] if rows else ""
        self.draw()

    def select(self, agent_id: str) -> None:
        self.selected = agent_id
        self.draw()
        if self.on_select:
            self.on_select(agent_id)

    def _press(self, e: tk.Event) -> None:
        for cid in self.find_overlapping(e.x - 1, e.y - 1, e.x + 1, e.y + 1):
            aid = self.card_of.get(cid)
            if aid:
                self.select(aid)
                return

    def draw(self) -> None:
        p = palette5(self.assets.theme)
        self.delete("all")
        self.card_of = {}
        self.configure(background=p["panel"])
        if not self.rows:
            self.create_text(self.GAP, self.GAP + 10, anchor="w", fill=p["text_dim"], font=font5("body"),
                             text="No AI team yet — plan the project in the Workbench.")
            self.configure(height=40)
            return
        cw, ch, gap = self.CARD_W, self.CARD_H, self.GAP
        per_row = max(1, (max(self.winfo_width(), cw + 2 * gap) - gap) // (cw + gap))
        state_role = {"Stuck": "danger", "Overloaded": "warn", "Working": "active", "Idle": "warn", "Free": "go"}
        for i, r in enumerate(self.rows):
            x0 = gap + (i % per_row) * (cw + gap)
            y0 = gap + (i // per_row) * (ch + gap)
            sel = r["agent_id"] == self.selected
            card = self.create_rectangle(x0, y0, x0 + cw, y0 + ch, fill=p["raised"],
                                         outline=p["active"] if sel else p["line"], width=2 if sel else 1)
            self.card_of[card] = r["agent_id"]
            hx, hy = x0 + 26, y0 + 28
            items = [self.create_image(hx, hy, image=self.assets.sprite("hex")),
                     self.create_text(hx, hy, text=str(r["number"]), fill=p["go_hi"], font=font5("capsule")),
                     self.create_text(x0 + 48, y0 + 20, anchor="w", text=r["name"], fill=p["text"],
                                      font=font5("title")),
                     self.create_text(x0 + 48, y0 + 38, anchor="w", text=r["role_text"], fill=p["text_dim"],
                                      font=font5("small"))]
            word = state_of(r)
            col = p[state_role[word]]
            items += [self.create_oval(x0 + cw - 84, y0 + 15, x0 + cw - 76, y0 + 23, fill=col, outline=col),
                      self.create_text(x0 + cw - 70, y0 + 19, anchor="w", text=word, fill=col, font=font5("small"))]
            now = f"Now: {r['current_task_id']} · {r['current_stage'].replace('_', ' ')}" if r["current_task_id"] \
                else "Now: no task"
            items.append(self.create_text(x0 + 14, y0 + 62, anchor="w", text=now, fill=p["text"], font=font5("small")))
            # workload bar: this AI's share of the open work
            bx0, bx1, by = x0 + 14, x0 + cw - 14, y0 + 80
            items.append(self.create_rectangle(bx0, by, bx1, by + 5, fill=p["field"], outline=""))
            if r["load_share"]:
                items.append(self.create_rectangle(bx0, by, bx0 + (bx1 - bx0) * min(1.0, r["load_share"]), by + 5,
                                                   fill=col, outline=""))
            items.append(self.create_text(x0 + 14, y0 + 97, anchor="w", text=stats_line(r), fill=p["text_dim"],
                                          font=font5("small")))
            for it in items:
                self.card_of[it] = r["agent_id"]
        rows_n = (len(self.rows) + per_row - 1) // per_row
        want = gap + rows_n * (ch + gap)
        if int(self.cget("height")) != want:
            self.configure(height=want)
