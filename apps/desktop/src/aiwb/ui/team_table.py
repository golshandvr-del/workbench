"""The AI team table (roadmap 5.9.0): one row per AI — name · role · model label · note.

Used by the New Project wizard (step 2) and by Agents › Edit team. The first row is always the project manager (its
role cannot change); the number box above the table sets how many AIs work besides the project manager. The widget
only edits rows; :mod:`aiwb.v2.team_setup` checks and stores them.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from aiwb.v2 import team_setup

ROLE_LABELS = [label for label, _role in team_setup.ROLE_CHOICES]


class TeamTable(ttk.Frame):
    """Editable team rows. ``rows()`` returns ``[{agent_id?, name, role, model, note}]`` (role = model role)."""

    def __init__(self, master: tk.Misc, rows: list[dict[str, Any]] | None = None, *, show_note: bool = True,
                 on_change: Callable[[], Any] | None = None, **kw: Any) -> None:
        super().__init__(master, **kw)
        self.show_note = show_note
        self.on_change = on_change
        self._rows: list[dict[str, Any]] = [dict(r) for r in (rows or team_setup.default_rows())]
        self._vars: list[dict[str, tk.Variable]] = []
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="How many AIs work in parallel (besides the project manager)?").pack(side="left")
        self.count_var = tk.StringVar(value=str(max(1, len(self._rows) - 1)))
        self.count_box = ttk.Spinbox(head, from_=1, to=team_setup.MAX_WORKERS, width=4, textvariable=self.count_var,
                                     command=self._count_changed)
        self.count_box.pack(side="left", padx=(8, 0))
        self.count_box.bind("<Return>", lambda _e: self._count_changed())
        self.count_box.bind("<FocusOut>", lambda _e: self._count_changed())
        self.grid_frame = ttk.Frame(self)
        self.grid_frame.pack(fill="x", pady=(8, 0))
        self._draw()

    # -- data
    def _collect(self) -> None:
        for row, v in zip(self._rows, self._vars):
            row["name"] = v["name"].get().strip()
            if "role" in v:
                row["role"] = team_setup.role_of(v["role"].get())
            row["model"] = v["model"].get().strip()
            if "note" in v:
                row["note"] = v["note"].get().strip()

    def rows(self) -> list[dict[str, Any]]:
        self._collect()
        return [dict(r) for r in self._rows]

    def set_count(self, workers: int) -> None:
        self._collect()
        self._rows = team_setup.resize_rows(self._rows, workers)
        self.count_var.set(str(len(self._rows) - 1))
        self._draw()
        if self.on_change:
            self.on_change()

    def _count_changed(self) -> None:
        try:
            n = int(self.count_var.get())
        except ValueError:
            n = len(self._rows) - 1
        n = max(1, min(team_setup.MAX_WORKERS, n))
        if n != len(self._rows) - 1:
            self.set_count(n)
        else:
            self.count_var.set(str(n))

    # -- view
    def _draw(self) -> None:
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self._vars = []
        g = self.grid_frame
        cols = ["#", "Name", "Role", "Model / account (label)"] + (["Note"] if self.show_note else [])
        for c, text in enumerate(cols):
            ttk.Label(g, text=text, style="Hint.TLabel").grid(row=0, column=c, sticky="w", padx=(0, 6))
        g.columnconfigure(1, weight=2)
        g.columnconfigure(3, weight=1)
        if self.show_note:
            g.columnconfigure(4, weight=2)
        for i, row in enumerate(self._rows):
            r = i + 1
            ttk.Label(g, text=str(i) if i else "PM").grid(row=r, column=0, sticky="w", padx=(0, 6), pady=2)
            v: dict[str, tk.Variable] = {"name": tk.StringVar(value=row.get("name", "")),
                                         "model": tk.StringVar(value=row.get("model", ""))}
            ttk.Entry(g, textvariable=v["name"], width=22).grid(row=r, column=1, sticky="ew", padx=(0, 6), pady=2)
            if i == 0:
                ttk.Label(g, text=team_setup.PM_ROLE_LABEL).grid(row=r, column=2, sticky="w", padx=(0, 6))
            else:
                v["role"] = tk.StringVar(value=team_setup.ROLE_LABEL.get(row.get("role", "implementer"), "Developer"))
                ttk.Combobox(g, textvariable=v["role"], values=ROLE_LABELS, state="readonly", width=16).grid(
                    row=r, column=2, sticky="w", padx=(0, 6), pady=2)
            ttk.Entry(g, textvariable=v["model"], width=16).grid(row=r, column=3, sticky="ew", padx=(0, 6), pady=2)
            if self.show_note:
                v["note"] = tk.StringVar(value=row.get("note", ""))
                ttk.Entry(g, textvariable=v["note"], width=24).grid(row=r, column=4, sticky="ew", pady=2)
            self._vars.append(v)

    def entries(self) -> list[dict[str, tk.Variable]]:
        """The variables of every row (tests type into the real entries through these)."""
        return self._vars
