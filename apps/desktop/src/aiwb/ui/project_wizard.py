"""New Project wizard (roadmap 5.9.0, audit A1/A2/A8/A9): one window, three steps, the only place for project data.

1. **Project** — name · parent folder (create mode) · goal · preset → platform · technical details (optional,
   collapsed: constraints, README, Git).
2. **Team** — "how many AIs in parallel?" and one row per AI: name · role · model label · note (:class:`TeamTable`).
3. **Answers** — the answer format the AIs are asked for. AIWB file blocks are what the guided loop reads today;
   Strict JSON and GPT ZIP are shown but disabled until their readers arrive (5.10.0), so nothing is promised that
   the app cannot do yet.

``mode="start"`` is the same window without the folder fields; it replaces the five chained "Start the project"
questions for projects added from an existing folder and for "Change the project details…".

The wizard only collects and checks; ``on_finish(data)`` does the work and may raise to show an error inline.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable

from aiwb.v2 import team_setup

from . import layout as ui_layout
from .team_table import TeamTable

STEPS = ("Project", "Team", "Answers")
FORMAT_NOTE = {"json": "reader arrives in 5.10.0", "zip": "reader arrives in 5.10.0"}


class ProjectWizard:
    """``data`` passed to ``on_finish``: name, parent, goal, preset, platform, constraints, readme, git, team, format."""

    def __init__(self, master: tk.Misc, *, mode: str = "create", presets: tuple[str, ...] = (),
                 preset_platform: Callable[[str], str] | None = None, initial: dict[str, Any] | None = None,
                 on_finish: Callable[[dict[str, Any]], Any]) -> None:
        self.mode = mode
        self.on_finish = on_finish
        self.preset_platform = preset_platform or (lambda _p: "")
        init = dict(initial or {})
        self.win = tk.Toplevel(master)
        self.win.title("Create a new project" if mode == "create" else "Start the project")
        self.win.transient(master.winfo_toplevel())
        self.step = 0
        self.vars: dict[str, tk.Variable] = {
            "name": tk.StringVar(value=init.get("name", "")),
            "parent": tk.StringVar(value=init.get("parent", "")),
            "preset": tk.StringVar(value=init.get("preset", presets[0] if presets else "")),
            "platform": tk.StringVar(value=init.get("platform", "")),
            "constraints": tk.StringVar(value=init.get("constraints", "")),
            "readme": tk.BooleanVar(value=bool(init.get("readme", True))),
            "git": tk.BooleanVar(value=bool(init.get("git", False))),
            "format": tk.StringVar(value=init.get("format", "aiwb")),
        }
        self._platform_auto = not init.get("platform")

        outer = ttk.Frame(self.win, padding=18)
        outer.pack(fill="both", expand=True)
        self.title_var = tk.StringVar()
        ttk.Label(outer, textvariable=self.title_var, style="SectionTitle.TLabel").pack(anchor="w")
        self.crumb_var = tk.StringVar()
        ttk.Label(outer, textvariable=self.crumb_var, style="Hint.TLabel").pack(anchor="w", pady=(2, 10))
        self.body = ttk.Frame(outer)
        self.body.pack(fill="both", expand=True)
        self.error_var = tk.StringVar()
        ttk.Label(outer, textvariable=self.error_var, style="Danger.TLabel", wraplength=700).pack(anchor="w", pady=(6, 0))
        bar = ttk.Frame(outer)
        bar.pack(fill="x", pady=(10, 0))
        self.cancel_btn = ttk.Button(bar, text="Cancel", command=self.win.destroy)
        self.cancel_btn.pack(side="right")
        self.next_btn = ttk.Button(bar, text="Next", style="Primary.TButton", command=self.next)
        self.next_btn.pack(side="right", padx=(0, 7))
        self.back_btn = ttk.Button(bar, text="Back", command=self.back)
        self.back_btn.pack(side="right", padx=(0, 7))

        self.pages = [self._page_project(presets, init), self._page_team(init), self._page_format()]
        self.show(0)
        ui_layout.place_dialog(self.win, 780, 620, master)
        try:
            self.win.grab_set()
        except tk.TclError:
            pass

    # -- pages
    def _field(self, parent: ttk.Frame, label: str, hint: str = "") -> None:
        ttk.Label(parent, text=label, style="FieldTitle.TLabel").pack(anchor="w", pady=(8, 2))
        if hint:
            ttk.Label(parent, text=hint, style="Hint.TLabel", wraplength=700).pack(anchor="w", pady=(0, 2))

    def _page_project(self, presets: tuple[str, ...], init: dict[str, Any]) -> ttk.Frame:
        f = ttk.Frame(self.body)
        self._field(f, "Project name", "Also the folder name." if self.mode == "create" else "")
        self.name_entry = ttk.Entry(f, textvariable=self.vars["name"])
        self.name_entry.pack(fill="x")
        if self.mode == "create":
            self._field(f, "Parent folder", "The project is created as parent folder / project name; an existing "
                                            "folder is never overwritten.")
            row = ttk.Frame(f)
            row.pack(fill="x")
            ttk.Entry(row, textvariable=self.vars["parent"]).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse…", command=self._browse).pack(side="left", padx=(7, 0))
        self._field(f, "Goal", "What should this project achieve? One or two sentences are enough.")
        self.goal_text = tk.Text(f, height=3, wrap="word", undo=True)
        self.goal_text.pack(fill="x")
        if init.get("goal"):
            self.goal_text.insert("1.0", init["goal"])
        if presets:
            self._field(f, "Kind of project")
            box = ttk.Combobox(f, textvariable=self.vars["preset"], values=presets, state="readonly")
            box.pack(fill="x")
            box.bind("<<ComboboxSelected>>", lambda _e: self._preset_changed())
        self._field(f, "Platform / technology", "Filled from the kind of project; change it freely.")
        plat = ttk.Entry(f, textvariable=self.vars["platform"])
        plat.pack(fill="x")
        plat.bind("<Key>", lambda _e: setattr(self, "_platform_auto", False))
        if self._platform_auto:
            self._preset_changed()
        self.details_btn = ttk.Button(f, text="Technical details (optional) ▸", command=self._toggle_details)
        self.details_btn.pack(anchor="w", pady=(10, 0))
        self.details = ttk.Frame(f)
        self._field(self.details, "Constraints", "For example: offline only, no paid libraries, must run on Windows 10.")
        ttk.Entry(self.details, textvariable=self.vars["constraints"]).pack(fill="x")
        if self.mode == "create":
            ttk.Checkbutton(self.details, text="Create a starter README.md", variable=self.vars["readme"]).pack(anchor="w", pady=(6, 0))
            ttk.Checkbutton(self.details, text="Initialize a local Git repository (requires Git for Windows)",
                            variable=self.vars["git"]).pack(anchor="w")
        return f

    def _page_team(self, init: dict[str, Any]) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="You decide how many AI chats work on this project and who they are. The project manager "
                          "plans the work; every other AI gets its own lane on the Mission Map, under the name you give "
                          "here. You can change the team later on the Agents page.", style="Hint.TLabel",
                  wraplength=720).pack(anchor="w", pady=(0, 8))
        self.team = TeamTable(f, init.get("team") or team_setup.default_rows())
        self.team.pack(fill="x")
        return f

    def _page_format(self) -> ttk.Frame:
        f = ttk.Frame(self.body)
        ttk.Label(f, text="How should the AIs return files? Workbench reads the answer and shows every file before "
                          "anything is written.", style="Hint.TLabel", wraplength=720).pack(anchor="w", pady=(0, 8))
        self.format_buttons: dict[str, ttk.Radiobutton] = {}
        for key, label in team_setup.ANSWER_FORMATS:
            ok = key in team_setup.SUPPORTED_FORMATS
            text = label if ok else f"{label} — {FORMAT_NOTE.get(key, 'not available yet')}"
            rb = ttk.Radiobutton(f, text=text, value=key, variable=self.vars["format"],
                                 state="normal" if ok else "disabled")
            rb.pack(anchor="w", pady=3)
            self.format_buttons[key] = rb
        ttk.Label(f, text="AIWB file blocks are plain text that survive copy and paste from ChatGPT, Claude, Gemini and "
                          "others.", style="Hint.TLabel", wraplength=720).pack(anchor="w", pady=(10, 0))
        return f

    # -- behaviour
    def _browse(self) -> None:
        start = self.vars["parent"].get().strip()
        chosen = filedialog.askdirectory(title="Choose where to create the project", parent=self.win,
                                         initialdir=start if Path(start).is_dir() else str(Path.home()))
        if chosen:
            self.vars["parent"].set(chosen)

    def _preset_changed(self) -> None:
        if self._platform_auto:
            self.vars["platform"].set(self.preset_platform(self.vars["preset"].get()))

    def _toggle_details(self) -> None:
        if self.details.winfo_ismapped():
            self.details.pack_forget()
            self.details_btn.configure(text="Technical details (optional) ▸")
        else:
            self.details.pack(fill="x", after=self.details_btn)
            self.details_btn.configure(text="Technical details (optional) ▾")

    def show(self, step: int) -> None:
        self.step = step
        for p in self.pages:
            p.pack_forget()
        self.pages[step].pack(fill="both", expand=True)
        head = "Create a new project" if self.mode == "create" else "Start the project"
        self.title_var.set(f"{head} — {STEPS[step]}")
        self.crumb_var.set("   ›   ".join(f"{i + 1}  {s}" if i != step else f"[{i + 1}  {s}]" for i, s in enumerate(STEPS)))
        self.back_btn.configure(state="normal" if step else "disabled")
        last = "Create project" if self.mode == "create" else "Start the project"
        self.next_btn.configure(text=last if step == len(STEPS) - 1 else "Next")
        self.error_var.set("")
        if step == 0:
            self.name_entry.focus_set()

    def goal(self) -> str:
        return self.goal_text.get("1.0", "end-1c").strip()

    def problems(self, step: int) -> list[str]:
        """What blocks leaving ``step`` (empty = fine)."""
        out: list[str] = []
        if step == 0:
            if not self.vars["name"].get().strip() and self.mode == "create":
                out.append("Give the project a name.")
            if self.mode == "create" and not Path(self.vars["parent"].get().strip() or ".").expanduser().is_dir():
                out.append("Choose an existing parent folder.")
            if not self.goal():
                out.append("Describe the goal of the project (one or two sentences).")
        elif step == 1:
            try:
                out += [p[0].upper() + p[1:] + "." for p in team_setup.check_rows(self.team.rows())]
            except Exception as exc:  # noqa: BLE001 — shown to the user, never a traceback
                out.append(str(exc))
        elif step == 2 and self.vars["format"].get() not in team_setup.SUPPORTED_FORMATS:
            out.append("Choose AIWB file blocks; the other formats arrive in 5.10.0.")
        return out

    def data(self) -> dict[str, Any]:
        return {"name": self.vars["name"].get().strip(), "parent": self.vars["parent"].get().strip(),
                "goal": self.goal(), "preset": self.vars["preset"].get(), "platform": self.vars["platform"].get().strip(),
                "constraints": self.vars["constraints"].get().strip(), "readme": bool(self.vars["readme"].get()),
                "git": bool(self.vars["git"].get()), "team": self.team.rows(), "format": self.vars["format"].get()}

    def back(self) -> None:
        if self.step:
            self.show(self.step - 1)

    def next(self) -> Any:
        problems = self.problems(self.step)
        if problems:
            self.error_var.set(" ".join(problems))
            return None
        if self.step < len(STEPS) - 1:
            self.show(self.step + 1)
            return None
        try:
            out = self.on_finish(self.data())
        except Exception as exc:  # noqa: BLE001 — the message is the user's next action, not a traceback
            self.error_var.set(str(exc))
            return None
        if self.win.winfo_exists():
            self.win.destroy()
        return out
