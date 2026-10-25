"""Project Workbench window (roadmap 2.3.0 stage 3, ADR-007).

Frame: Project Bar · Sidebar · Next Action Strip · Workspace view · collapsible
Inspector · Status Footer. Grid weights + breakpoints (no fixed-only geometry);
the window is clamped to the screen work area. All data comes from
:class:`WorkspaceController`; buttons only call controller methods.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

from .. import i18n
from ..v2.models import ModelError
from ..ui import layout as ui_layout
from . import theme
from .controller import SECTIONS, WorkspaceController

SCROLL_VIEWS = {"plan", "project"}  # 5.11.0: three sections; old keys are aliases (controller.SECTION_ALIASES)


class WorkspaceWindow:
    """The Project Workbench view.

    3.0.0 (ADR-009): normally *embedded* as a page of the main window (``host`` = a frame
    of the single shell) — no second window, no own theme/language/mode controls; those are
    application-wide in Settings. The stand-alone Toplevel form is kept only for tests/tools.
    """

    def __init__(self, parent: tk.Misc, wc: WorkspaceController, *, clipboard: Callable[[str], None],
                 geometry: str = "", host: tk.Misc | None = None, on_home: Callable[[], Any] | None = None) -> None:
        self.wc = wc
        self.clipboard = clipboard
        self.on_home = on_home  # 5.11.0: the next step is done on Home's card; the strip only points there
        self.last_prompt = ""
        self.last_handoff_id = ""
        self.embedded = host is not None
        if self.embedded:
            self.win = ttk.Frame(host, style="WS.TFrame")
            self.win.pack(fill="both", expand=True)
            self.top = self.win.winfo_toplevel()
            self.style = ttk.Style(self.win)
            self.pal = theme.palette(wc.theme)
        else:
            self.win = tk.Toplevel(parent)
            self.top = self.win
            self.win.title(f"{wc.ctl.root.name} — AI Workbench")
            self.win.minsize(*theme.MIN_SIZE)
            self.style = ttk.Style(self.win)
            self.pal = theme.apply(self.style, wc.theme)
            self.win.configure(background=self.pal["bg"])
            self._place(geometry)
        self.layout = theme.layout_for(theme.DEFAULT_SIZE[0])
        self._build()
        self.win.bind("<Configure>", self._on_configure, add="+")
        if not self.embedded:
            self.win.bind("<Control-i>", lambda _e: self.toggle_inspector())
            self.win.bind("<Control-b>", lambda _e: self.toggle_sidebar())
            for i, key in enumerate(SECTIONS, start=1):
                self.win.bind(f"<Alt-Key-{i}>", lambda _e, k=key: self.show(k))
            self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.show(wc.section)

    def apply_prefs(self) -> None:
        """Called by the shell after an application-wide theme/language/mode change."""
        self.pal = theme.palette(self.wc.theme)
        self.mode_var.set(self.wc.mode)
        self.lang_var.set(self.wc.lang)
        self.theme_var.set(self.wc.theme)
        self._arrange()
        self.show(self.wc.section)

    # -- geometry
    def _work_area(self) -> tuple[int, int, int, int]:
        try:
            return 0, 0, self.win.winfo_screenwidth(), self.win.winfo_screenheight() - 48  # leave room for the taskbar
        except tk.TclError:
            return 0, 0, *theme.DEFAULT_SIZE

    def _place(self, geometry: str) -> None:
        if geometry:
            self.win.geometry(geometry)
            return
        area = self._work_area()
        w, h = theme.DEFAULT_SIZE
        x, y, w, h = theme.clamp_to_work_area((area[2] - w) // 2, (area[3] - h) // 2, w, h, area)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _on_configure(self, event: Any) -> None:
        if event.widget is not self.win:
            return
        new = theme.layout_for(self.top.winfo_width() if self.embedded else event.width)
        if new != self.layout:
            self.layout = new
            self._arrange()

    # -- structure
    def _build(self) -> None:
        w = self.win
        w.columnconfigure(0, weight=1)
        w.rowconfigure(2, weight=1)
        # Project bar
        self.bar = ttk.Frame(w, style="WS.TFrame", padding=(theme.SPACING["l"], theme.SPACING["m"]))
        self.bar.grid(row=0, column=0, sticky="ew")
        self.bar.columnconfigure(1, weight=1)
        self.sidebar_btn = ttk.Button(self.bar, text="☰", width=3, command=self.toggle_sidebar)
        self.sidebar_btn.grid(row=0, column=0, padx=(0, 8))
        self.title_var = tk.StringVar()
        ttk.Label(self.bar, textvariable=self.title_var, style="WS.Title.TLabel").grid(row=0, column=1, sticky="w")
        self.pub_var = tk.StringVar()
        ttk.Label(self.bar, textvariable=self.pub_var, style="WS.Muted.TLabel").grid(row=1, column=1, sticky="w")
        ctl = ttk.Frame(self.bar, style="WS.TFrame")
        ctl.grid(row=0, column=2, rowspan=2, sticky="e")
        self.mode_var = tk.StringVar(value=self.wc.ctl.mode)
        self.mode_box = ttk.Combobox(ctl, textvariable=self.mode_var, values=["simple", "advanced"], width=9, state="readonly")
        if not self.embedded:
            self.mode_box.pack(side="left", padx=4)
        self.mode_box.bind("<<ComboboxSelected>>", lambda _e: self._set_mode())
        self.lang_var = tk.StringVar(value=self.wc.lang)
        self.lang_box = ttk.Combobox(ctl, textvariable=self.lang_var, values=list(i18n.LANGUAGES), width=4, state="readonly")
        if not self.embedded:
            self.lang_box.pack(side="left", padx=4)
        self.lang_box.bind("<<ComboboxSelected>>", lambda _e: self._set_lang())
        self.theme_var = tk.StringVar(value=self.wc.theme)
        self.theme_box = ttk.Combobox(ctl, textvariable=self.theme_var, values=list(theme.THEMES), width=6, state="readonly")
        if not self.embedded:
            self.theme_box.pack(side="left", padx=4)
        self.theme_box.bind("<<ComboboxSelected>>", lambda _e: self._set_theme())
        self.inspector_btn = ttk.Button(ctl, text="ⓘ", width=3, command=self.toggle_inspector)
        self.inspector_btn.pack(side="left", padx=4)
        # Next action strip
        self.next_frame = ttk.Frame(w, style="WS.Surface.TFrame", padding=(theme.SPACING["l"], theme.SPACING["m"]))
        self.next_frame.grid(row=1, column=0, sticky="ew", padx=theme.SPACING["l"])
        self.next_frame.columnconfigure(0, weight=1)
        self.next_var = tk.StringVar()
        self.next_label = ttk.Label(self.next_frame, textvariable=self.next_var, style="WS.Next.TLabel", wraplength=900)
        self.next_label.grid(row=0, column=0, sticky="w")
        self.next_explain_var = tk.StringVar()
        self.next_explain = ttk.Label(self.next_frame, textvariable=self.next_explain_var, style="WS.Muted.TLabel",
                                      wraplength=900)
        self.next_explain.grid(row=1, column=0, sticky="w")
        # Phase bar (roadmap 4.0.0): where the project is in the owner's flowchart.
        self.flow_var = tk.StringVar()
        ttk.Label(self.next_frame, textvariable=self.flow_var, style="WS.Muted.TLabel").grid(row=2, column=0, sticky="w")
        # 5.11.0 (A7): one home per command — the step's buttons and the paste box live on Home's Next-step card
        self.next_btn = ttk.Button(self.next_frame, text="Open on Home", style="WS.Primary.TButton", command=self.go_home)
        self.next_btn._aiwb_link = "home"  # type: ignore[attr-defined]  # App Map: a link, not a second command
        self.next_btn.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0))
        self.guide_step: dict[str, Any] = {}
        # Body: sidebar | center | inspector
        self.body = ttk.Frame(w, style="WS.TFrame")
        self.body.grid(row=2, column=0, sticky="nsew", padx=theme.SPACING["l"], pady=theme.SPACING["m"])
        self.body.rowconfigure(0, weight=1)
        self.sidebar = ttk.Frame(self.body, style="WS.Sidebar.TFrame", padding=theme.SPACING["s"])
        self.nav: dict[str, ttk.Button] = {}
        for key in SECTIONS:
            b = ttk.Button(self.sidebar, style="WS.Nav.TButton", command=lambda k=key: self.show(k))
            b.pack(fill="x", pady=1)
            self.nav[key] = b
        self.center = ttk.Frame(self.body, style="WS.TFrame")
        self.center.rowconfigure(0, weight=1)
        self.center.columnconfigure(0, weight=1)
        self.inspector = ttk.Frame(self.body, style="WS.Surface.TFrame", padding=theme.SPACING["m"])
        self.inspector.columnconfigure(0, weight=1)
        self.insp_title = tk.StringVar()
        ttk.Label(self.inspector, textvariable=self.insp_title, style="WS.Next.TLabel", wraplength=300).grid(row=0, column=0, sticky="w")
        self.insp_text = tk.Text(self.inspector, height=12, width=36, wrap="word", relief="flat")
        self.insp_text.grid(row=1, column=0, sticky="nsew", pady=4)
        self.inspector.rowconfigure(1, weight=1)
        self.insp_actions = ttk.Frame(self.inspector, style="WS.Surface.TFrame")
        self.insp_actions.grid(row=2, column=0, sticky="ew")
        # Footer
        self.status_var = tk.StringVar()
        ttk.Label(w, textvariable=self.status_var, style="WS.Muted.TLabel", padding=(theme.SPACING["l"], 2)).grid(
            row=3, column=0, sticky="ew")
        self.views: dict[str, ttk.Frame] = {}
        self._arrange()

    def _arrange(self) -> None:
        """Place sidebar / center / inspector for the current width breakpoint and open/closed panels."""
        for child in (self.sidebar, self.center, self.inspector):
            child.grid_forget()
        for c in range(3):
            self.body.columnconfigure(c, weight=0)
        self.body.rowconfigure(1, weight=0)
        col = 0
        if self.wc.sidebar_open:
            self.sidebar.grid(row=0, column=0, sticky="ns", padx=(0, theme.SPACING["m"]), rowspan=2)
            col = 1
        self.center.grid(row=0, column=col, sticky="nsew")
        self.body.columnconfigure(col, weight=1)
        if self.wc.inspector_open:
            if self.layout["inspector"] == "side":
                self.inspector.grid(row=0, column=col + 1, sticky="nsew", padx=(theme.SPACING["m"], 0))
            else:
                self.inspector.grid(row=1, column=col, sticky="nsew", pady=(theme.SPACING["m"], 0))
                self.body.rowconfigure(1, weight=0)
        compact = self.layout["sidebar"] == "compact"
        for key, b in self.nav.items():
            b.configure(text=self.wc.section_label(key, compact=compact))

    # -- preferences (ui.json only)
    def toggle_inspector(self) -> None:
        self.wc.set_inspector(not self.wc.inspector_open)
        self._arrange()

    def toggle_sidebar(self) -> None:
        self.wc.set_sidebar(not self.wc.sidebar_open)
        self._arrange()

    def _set_mode(self) -> None:
        self.wc.set_mode(self.mode_var.get())
        self.refresh()

    def _set_lang(self) -> None:
        self.wc.set_language(self.lang_var.get())
        self._arrange()
        self.show(self.wc.section)

    def _set_theme(self) -> None:
        self.wc.set_theme(self.theme_var.get())
        if self.embedded:
            return  # the shell re-themes the whole application (AppPrefs observer)
        self.pal = theme.apply(self.style, self.wc.theme)
        self.win.configure(background=self.pal["bg"])
        self.show(self.wc.section)

    # -- navigation
    def show(self, key: str) -> None:
        self.wc.set_section(key)
        key = self.wc.section  # 5.11.0: an old key (overview, tasks, team, …) opens the section that now holds it
        for k, b in self.nav.items():
            b.configure(style="WS.NavActive.TButton" if k == key else "WS.Nav.TButton")
        for v in self.views.values():
            v.destroy()
        self.views = {}
        if key in SCROLL_VIEWS:  # content-height views scroll instead of being cut off (3.1.0)
            holder = ui_layout.ScrollPage(self.center, style="WS.TFrame")
            holder.grid(row=0, column=0, sticky="nsew")
            frame = holder.body
            frame.configure(style="WS.TFrame")
            self.views[key] = holder
        else:
            frame = ttk.Frame(self.center, style="WS.TFrame")
            frame.grid(row=0, column=0, sticky="nsew")
            self.views[key] = frame
        frame.columnconfigure(0, weight=1)
        getattr(self, f"_view_{key}")(frame)
        self.refresh()

    def refresh(self) -> None:
        bar = self.wc.project_bar()
        self.title_var.set(f"{bar['name']}" + (f" — {bar['goal'][:80]}" if bar["goal"] else ""))
        self.pub_var.set(bar["publish"])
        steps = self.wc.guide_steps()
        st = self.guide_step = steps[0]
        aname = str(((self.wc.ctl.state().get("agents") or {}).get(st["agent_id"]) or {}).get("name") or st["agent_id"])
        who = "" if st["agent_id"] == "you" or aname in st["title"] else f"  [{aname}]"  # 5.13.0 (B4): the name
        self.next_var.set(("← " if self.wc.rtl else "→ ") + "Next step: " + st["title"] + who)
        self.next_explain_var.set(st["explain"] + (f"  ({len(steps) - 1} more open)" if len(steps) > 1 else ""))
        self.flow_var.set(self.wc.flow_text())
        self.next_label.configure(anchor="e" if self.wc.rtl else "w", justify="right" if self.wc.rtl else "left")
        self._render_inspector()

    def _render_inspector(self) -> None:
        data = self.wc.inspector()
        self.insp_title.set(data["title"])
        self.insp_text.delete("1.0", "end")
        self.insp_text.insert("1.0", data["text"])
        for c in self.insp_actions.winfo_children():
            c.destroy()
        for key, label in data["actions"]:
            ttk.Button(self.insp_actions, text=label, command=lambda k=key: self.inspector_action(k)).pack(fill="x", pady=1)

    def inspector_action(self, key: str, confirm: bool | None = None) -> Any:
        if key == "bind_chat":
            return self.dialog_bind_chat(self.wc.selection[1])
        if key == "change_request":
            return self.dialog_change_request(self.wc.selection[1])
        if key == "start_task":
            warn = self.wc.start_warning(self.wc.selection[1])
            if warn:
                if confirm is None:
                    confirm = messagebox.askyesno("AI Workbench", warn, parent=self.win)
                if not confirm:
                    self.status_var.set(self.wc.tr(("Kept the existing attempt; nothing changed.",
                                                    "تلاش قبلی حفظ شد؛ چیزی تغییر نکرد.")))
                    return None
        out = self._guard(lambda: self.wc.run_action(key))
        if key == "start_task" and isinstance(out, dict):
            self.last_handoff_id = out["handoff_id"]
            self.last_prompt = out["prompt"]
            self.status_var.set(self.wc.tr(("Prompt ready — copy it from Tasks → prompt box. Not sent yet.",
                                            "پرامپت آماده است — از بخش Tasks کپی کنید. هنوز ارسال نشده.")))
            self.show("tasks")
        elif key == "open_task":
            self.show("tasks")
        elif key == "confirm_sent" and isinstance(out, dict):
            self.status_var.set(self.wc.tr(("Recorded: you sent the prompt (your confirmation time). Paste the answer when you have it.",
                                            "ثبت شد: پرامپت را ارسال کردید (زمان تأیید شما). وقتی پاسخ را گرفتید Paste کنید.")))
            self.show("tasks")
        else:
            self.refresh()
        return out

    def _guard(self, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except ModelError as exc:
            self.status_var.set(str(exc))
            return None

    def go_home(self) -> Any:
        """The strip's button (5.11.0): show Home, whose Next-step card does the step."""
        if self.on_home is None:
            self.status_var.set("Do this step on Home: the Next-step card has its buttons and the paste box.")
            return None
        return self.on_home()

    def do_next(self) -> Any:
        """Run the primary action of the guide's first step (3.5.0; no button since 5.11.0 — Home's card has it)."""
        st = self.guide_step or self.wc.guide_steps()[0]
        primary = next(a for a in st["actions"] if a["primary"])
        return self.guide_action(st["key"], primary["id"])

    INPUT_PROMPTS = {"goal": "What should this project achieve? (one or two sentences)",
                     "name": "Project name (optional)", "platform": "Platform / technology (optional)",
                     "constraints": "Constraints (optional)",
                     "ais": "How many AI chats can you use at the same time? (1-12, optional)", "note": "Note (optional)",
                     "reason": "Reason", "rationale": "Why? (kept in the decision log)", "choice": "Your decision",
                     "result": "Result: passed or failed", "run_id": "Run ID / build number (optional)",
                     "commit_sha": "Commit SHA of the release", "tag": "Tag (optional, default v<version>)"}

    def _ask_text(self, title: str) -> str:
        """Multi-line paste box for a whole model answer."""
        if hasattr(self, "answer_text") and self.answer_text.winfo_exists() and self.answer_text.get("1.0", "end-1c").strip():
            return self.answer_text.get("1.0", "end-1c")
        from ..ui.paste_box import ask_answer   # 5.10.0: live diagnosis + Load ZIP…
        try:
            state = self.wc.ctl.state()
        except Exception:  # noqa: BLE001 - the diagnosis works without a state (no revision checks)
            state = None
        return ask_answer(self.win, title, state=state, primary_style="WS.Primary.TButton")

    def _start_form(self, key: str, action: str, label: str) -> Any:
        """"Start the project…" / "Change the project details…": the New Project wizard without the folder fields.

        Prefilled from what the project already knows (goal, brief, the user's team or N developers), so nothing is
        asked twice; Finish sends brief + team to the guide in one step. Non-blocking: returns the wizard.
        """
        from ..ui.project_wizard import ProjectWizard
        from ..v2 import team_setup
        st = self.wc.ctl.state()
        settings = st.get("settings") or {}
        brief = settings.get("brief") or {}
        initial = {"name": brief.get("name", "") or self.wc.ctl.root.name, "goal": settings.get("goal", ""),
                   "platform": brief.get("platform", ""), "constraints": brief.get("constraints", ""),
                   "team": team_setup.start_rows(st), "format": settings.get("answer_format", "aiwb")}
        result: dict[str, Any] = {}

        def finish(d: dict[str, Any]) -> Any:
            out = self.wc.guide_perform(key, action, goal=d["goal"], name=d["name"], platform=d["platform"],
                                        constraints=d["constraints"], team=d["team"], answer_format=d["format"])
            result["out"] = out
            if out.get("prompt"):
                self.last_prompt, self.last_handoff_id = out["prompt"], out.get("handoff_id", "")
            self.show(self.wc.section)
            self.status_var.set(out["message"])
            return out
        self.start_form = ProjectWizard(self.win, mode="start", initial=initial, on_finish=finish)
        self.start_form.win.title(label.rstrip("…"))
        return self.start_form

    def guide_action(self, key: str, action: str, inputs: dict[str, Any] | None = None) -> Any:
        """Ask for the inputs an action needs (or take ``inputs``), perform it, show/copy the prompt it yields."""
        step = next((s for s in self.wc.guide_steps() if s["key"] == key), None)
        if step is None:
            self.status_var.set("This step is no longer open.")
            self.refresh()
            return None
        act = next((a for a in step["actions"] if a["id"] == action), None)
        if act is None:
            return None
        inp = dict(inputs or {})
        if inputs is None and action == "design":
            return self._start_form(key, action, act["label"])  # 5.9.0: one window, not five questions (A8)
        if inputs is None:
            for need in act["needs"]:
                if need == "text":
                    inp["text"] = self._ask_text(act["label"])
                    if not inp["text"].strip():
                        return None
                else:
                    v = simpledialog.askstring(act["label"], self.INPUT_PROMPTS.get(need, need), parent=self.win)
                    if v is None:
                        if "(optional" in self.INPUT_PROMPTS.get(need, ""):
                            v = ""
                        else:
                            return None
                    inp[need] = v
        out = self._guard(lambda: self.wc.guide_perform(key, action, **inp))
        if out is None:
            return None
        if out.get("prompt"):
            self.last_prompt, self.last_handoff_id = out["prompt"], out.get("handoff_id", "")
            if action in ("copy", "copy_context"):  # 5.12.0: the requested files go to the clipboard too
                self.clipboard(out["prompt"])
        self.show(self.wc.section)
        self.status_var.set(out["message"])
        return out

    # -- views
    def _heading(self, parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text, style="WS.Title.TLabel", anchor="e" if self.wc.rtl else "w").grid(
            row=0, column=0, sticky="ew", pady=(0, 6))

    def _view_plan(self, f: ttk.Frame) -> None:
        """Plan & Tasks (5.11.0): progress · needs your attention · the plan to review · tasks with their prompt and
        answer · the queue of each AI · recent activity. (5.10.0: Overview + Tasks + the review part of Team.)"""
        ov = self.wc.overview()
        self._heading(f, self.wc.section_label("plan"))
        anchor = "e" if self.wc.rtl else "w"
        side = "right" if self.wc.rtl else "left"
        goal = ov["goal"] or self.wc.tr(("No goal yet. Start the project on Home (Next step).",
                                         "هنوز هدفی ثبت نشده. پروژه را از Home (قدم بعد) شروع کنید."))
        ttk.Label(f, text=goal, style="WS.TLabel", wraplength=700, anchor=anchor).grid(row=1, column=0, sticky="ew")
        self.progress_var = tk.StringVar(value=self.wc.progress_text(ov["progress"]))
        ttk.Label(f, textvariable=self.progress_var, style="WS.TLabel", anchor=anchor).grid(row=2, column=0, sticky="ew", pady=4)
        bar = ttk.Progressbar(f, maximum=max(ov["progress"]["total"], 1), value=ov["progress"]["done"])
        bar.grid(row=3, column=0, sticky="ew")
        self.progress_details = self.wc.progress_details(ov["progress"])
        counts = " · ".join(f"{i18n.status(k, self.wc.lang)[0]} {i18n.status(k, self.wc.lang)[1]}: {v}"
                            for k, v in sorted(ov["counts"].items()))
        ttk.Label(f, text="\n".join(self.progress_details + [counts or "—"]), style="WS.Muted.TLabel", wraplength=700, anchor=anchor).grid(row=4, column=0, sticky="ew", pady=4)
        att = ttk.LabelFrame(f, text=self.wc.tr(("Needs your attention", "نیازمند توجه شما")), padding=6)
        att.grid(row=5, column=0, sticky="ew", pady=6)
        self.attention_items = self.wc.attention(hide_seen=True)
        if not self.attention_items:
            ttk.Label(att, text=self.wc.tr(("Nothing needs your attention.", "موردی نیازمند توجه نیست."))).pack(anchor=anchor)
        else:
            self.att_tree = ttk.Treeview(att, columns=("item",), show="tree headings", style="WS.Treeview",
                                         height=min(8, len(self.attention_items) + 2))
            self.att_tree.heading("#0", text=self.wc.tr(("Group", "گروه")))
            self.att_tree.heading("item", text=self.wc.tr(("What and why", "چه چیزی و چرا")))
            self.att_tree.column("#0", width=220, stretch=False)
            self.att_tree.column("item", width=520, stretch=True)
            for item in self.attention_items:
                self.att_tree.insert("", "end", iid=item["key"], text=f"{item['rank']}. {item['rank_text']}",
                                     values=(self.wc.attention_text(item),))
            self.att_tree.pack(fill="x")
            self.att_tree.bind("<Double-1>", lambda _e: self.open_attention_selected())
            ab = ttk.Frame(att, style="WS.TFrame")
            ab.pack(fill="x", pady=(4, 0))
            ttk.Button(ab, text=self.wc.tr(("Open", "باز کردن")), command=self.open_attention_selected).pack(side=side)
            am = tk.Menu(ab, tearoff=False)
            am.add_command(label=self.wc.tr(("Mark as read", "خوانده شد")), command=self.mark_attention_seen)
            am.add_command(label=self.wc.tr(("Show read items", "نمایش خوانده‌شده‌ها")),
                           command=lambda: (self.wc.clear_seen(), self.show("plan")))
            ttk.Menubutton(ab, text="More", menu=am).pack(side=side, padx=4)
        self._proposal_review(f, 6)
        tb = ttk.LabelFrame(f, text=self.wc.tr(("Tasks", "وظایف")), padding=6)
        tb.grid(row=7, column=0, sticky="nsew", pady=6)
        self._tasks_box(tb)
        qf = ttk.LabelFrame(f, text="Queue of each AI (double-click a step to do it)", padding=6)
        qf.grid(row=8, column=0, sticky="ew", pady=(0, 6))
        self.queue_tree = ttk.Treeview(qf, columns=("step",), show="tree headings", style="WS.Treeview", height=6)
        self.queue_tree.heading("#0", text="Who")
        self.queue_tree.heading("step", text="Step")
        self.queue_tree.column("#0", width=200, stretch=False)
        self.queue_tree.column("step", width=540, stretch=True)
        self.queues = self.wc.guide_queues()
        names = {aid: (a.get("name") or aid) for aid, a in (self.wc.ctl.state().get("agents") or {}).items()}
        for agent, steps in sorted(self.queues.items(), key=lambda kv: (kv[0] != "you", kv[0])):
            node = self.queue_tree.insert("", "end", iid="q:" + agent, text="You" if agent == "you" else names.get(agent, agent),
                                          values=(f"{len(steps)} open",), open=True)
            for st in steps:
                self.queue_tree.insert(node, "end", iid=st["key"], text="", values=(st["title"],))
        self.queue_tree.pack(fill="x")
        self.queue_tree.bind("<Double-1>", lambda _e: self.do_queue_selected())
        act = ttk.LabelFrame(f, text=self.wc.tr(("Recent activity", "فعالیت اخیر")), padding=6)
        act.grid(row=9, column=0, sticky="ew")
        for rec in ov["recent"]:
            ttk.Label(act, text=self.wc.event_text(rec), style="TLabel").pack(anchor=anchor)

    def do_queue_selected(self, key: str = "") -> Any:
        """Primary action of the step selected in the per-AI queue."""
        if not key:
            sel = self.queue_tree.selection() if hasattr(self, "queue_tree") else ()
            key = sel[0] if sel else ""
        if not key or key.startswith("q:"):
            return None
        st = next((s for s in self.wc.guide_steps() if s["key"] == key), None)
        if st is None:
            return None
        return self.guide_action(key, next(a["id"] for a in st["actions"] if a["primary"]))

    def dialog_change_request(self, task_id: str, request: str | None = None, route: str | None = None) -> Any:
        """One place for 'fix this task' vs 'new task' vs 're-plan' (spec §12.3). Never edits silently."""
        if request is None:
            request = self._ask(self.wc.tr(("Request a change", "درخواست تغییر")),
                                self.wc.tr(("What should change?", "چه چیزی باید تغییر کند؟")))
        if not request:
            return None
        sug = self._guard(lambda: self.wc.suggest_change(task_id, request))
        if not sug:
            return None
        if route is None:
            names = " / ".join(f"{k} = {v}" for k, v in sug["choices"])
            hint = self.wc.tr(("Suggested: ", "پیشنهاد: ")) + f"{sug['route']} — {sug['label']} ({sug['why']})"
            if sug["ambiguous"]:
                hint += self.wc.tr((" — not sure, please choose.", " — مطمئن نیستم، لطفاً انتخاب کنید."))
            route = self._ask(self.wc.tr(("Choose the route", "انتخاب مسیر")), f"{hint}\n{names}", sug["route"])
            if not route:
                return None
        out = self._guard(lambda: self.wc.apply_change(task_id, route, request))
        if not out:
            return None
        self.status_var.set(out["message"])
        if out.get("prompt"):
            self.last_prompt, self.last_handoff_id = out["prompt"], ""
        if out.get("task_id"):
            self.wc.select("task", out["task_id"])
        self.show("tasks")
        return out

    def _attention_by_key(self, key: str) -> dict[str, Any] | None:
        return next((i for i in getattr(self, "attention_items", []) if i["key"] == key), None)

    def open_attention_selected(self, key: str = "") -> Any:
        if not key and hasattr(self, "att_tree"):
            key = next(iter(self.att_tree.selection()), "")
        item = self._attention_by_key(key)
        if not item:
            self.status_var.set(self.wc.tr(("Select an item first.", "ابتدا یک مورد انتخاب کنید.")))
            return None
        if item["kind"] == "more":
            self.attention_items = [i for i in self.attention_items if i["key"] != key] + item["hidden"]
            self.att_tree.delete(key)
            for h in item["hidden"]:
                self.att_tree.insert("", "end", iid=h["key"], text=f"{h['rank']}. {h['rank_text']}",
                                     values=(self.wc.attention_text(h),))
            return item["hidden"]
        section, ref = self.wc.open_attention(item)
        self.show(section)
        self.status_var.set(f"{item['ref']}: {item['ask']}")
        return section, ref

    def mark_attention_seen(self, keys: list[str] | None = None) -> set[str]:
        if keys is None:
            keys = list(self.att_tree.selection()) if hasattr(self, "att_tree") else []
        out = self.wc.mark_seen([k for k in keys if not k.startswith("more:")])
        self.show("plan")
        return out

    def _tasks_box(self, f: ttk.Frame) -> None:
        """The task list with the prompt to copy and the answer to check (Plan & Tasks › Tasks)."""
        f.columnconfigure(0, weight=1)
        cols = ("status", "stage", "owner")
        self.task_tree = ttk.Treeview(f, columns=cols, show="tree headings", style="WS.Treeview", height=8)
        self.task_tree.heading("stage", text=self.wc.tr(("Workflow", "گردش کار")))
        self.task_tree.column("stage", width=240, stretch=True)
        self.task_tree.heading("#0", text=self.wc.tr(("Task", "Task")))
        self.task_tree.heading("status", text=self.wc.tr(("Status", "وضعیت")))
        self.task_tree.heading("owner", text=self.wc.tr(("Agent", "Agent")))
        self.task_tree.column("#0", width=320, stretch=True)
        self.task_tree.column("status", width=200, stretch=False)
        self.task_tree.column("owner", width=150, stretch=False)
        sb = ttk.Scrollbar(f, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=sb.set)
        self.task_tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        for r in self.wc.task_rows():
            self.task_tree.insert("", "end", iid=r["task_id"], text=f"{r['task_id']} {r['title']}",
                                  values=(f"{r['symbol']} {r['status_text']}", r.get("stage_text", ""), r["owner"]))
        kind, ref = self.wc.selection
        if kind == "task" and self.task_tree.exists(ref):
            self.task_tree.selection_set(ref)
        self.task_tree.bind("<<TreeviewSelect>>", lambda _e: self._select_from(self.task_tree, "task"))
        pf = ttk.Frame(f, style="WS.TFrame")
        pf.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        pf.columnconfigure(0, weight=1)
        pf.columnconfigure(1, weight=1)
        ttk.Label(pf, text=self.wc.tr(("Prompt to copy (Workbench never sends it)", "پرامپت برای کپی (Workbench آن را ارسال نمی‌کند)"))).grid(row=0, column=0, sticky="w")
        ttk.Label(pf, text=self.wc.tr(("Paste the model's answer", "پاسخ مدل را Paste کنید"))).grid(row=0, column=1, sticky="w")
        self.prompt_text = tk.Text(pf, height=7, wrap="word")
        self.prompt_text.grid(row=1, column=0, sticky="nsew", padx=(0, 4))
        self.prompt_text.insert("1.0", self.last_prompt)
        self.answer_text = tk.Text(pf, height=7, wrap="word")
        self.answer_text.grid(row=1, column=1, sticky="nsew")
        bb = ttk.Frame(pf, style="WS.TFrame")
        bb.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        side = "right" if self.wc.rtl else "left"
        ttk.Button(bb, text=self.wc.tr(("Copy prompt", "کپی پرامپت")), command=self.do_copy).pack(side=side)
        ttk.Button(bb, text=self.wc.tr(("Check & import answer", "بررسی و ثبت پاسخ")), style="WS.Primary.TButton",
                   command=self.do_import).pack(side=side, padx=4)

    def _view_project(self, f: ttk.Frame) -> None:
        """Project settings (5.11.0): project details · the AI team and its manager · account profiles · charter start
        prompts · project tools. (5.10.0: Team + Files & Context + Versions & Builds + Settings.)"""
        self._heading(f, self.wc.section_label("project"))
        anchor = "e" if self.wc.rtl else "w"
        side = "right" if self.wc.rtl else "left"
        st = self.wc.ctl.state()
        settings = st.get("settings") or {}
        brief = settings.get("brief") or {}
        det = ttk.LabelFrame(f, text=self.wc.tr(("Project details", "مشخصات پروژه")), padding=6)
        det.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        facts = [("Goal", settings.get("goal", "")), ("Name", brief.get("name", "") or self.wc.ctl.root.name),
                 ("Platform", brief.get("platform", "")), ("Constraints", brief.get("constraints", "")),
                 ("Answer format", settings.get("answer_format", "") or "aiwb"), ("Folder", str(self.wc.ctl.root))]
        self.details_var = tk.StringVar(value="\n".join(f"{k}: {v or '—'}" for k, v in facts))
        ttk.Label(det, textvariable=self.details_var, wraplength=760, justify="left", anchor=anchor).pack(fill="x")
        ttk.Label(det, text="Change them on Home (Next step › More › Change the project details…) until the plan is "
                            "accepted. The AIs themselves: Agents › Edit team…", style="WS.Muted.TLabel",
                  wraplength=760, anchor=anchor).pack(fill="x", pady=(4, 0))
        team = ttk.LabelFrame(f, text=self.wc.tr(("AI team", "تیم AI")), padding=6)
        team.grid(row=2, column=0, sticky="nsew", pady=6)
        dash = self.wc.dashboard()
        c = dash["counts"]
        self.team_status_var = tk.StringVar(value=self.wc.tr(("Verified ", "تأییدشده ")) + str(c["verified"]) + " · "
                                            + self.wc.tr(("working ", "در حال کار ")) + str(c["working"]) + " · "
                                            + self.wc.tr(("waiting for your paste ", "منتظر Paste شما ")) + str(c["waiting_answer"]) + " · "
                                            + self.wc.tr(("blocked ", "مسدود ")) + str(c["blocked"]) + " · "
                                            + self.wc.tr(("needs action ", "نیازمند اقدام ")) + str(c["needs_action"]))
        bar = ttk.Frame(team, style="WS.TFrame")
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.team_status_var, style="WS.Muted.TLabel").pack(side=side, padx=4)
        self.team_filter = tk.StringVar()
        fe = ttk.Entry(bar, textvariable=self.team_filter, width=14)
        fe.pack(side=side)
        fe.bind("<KeyRelease>", lambda _e: self.fill_team())  # filters as you type (5.11.0: no Filter button)
        self.team_attention_only = tk.BooleanVar(value=dash["density"] == "compact")
        ttk.Checkbutton(bar, text=self.wc.tr(("needs action only", "فقط نیازمند اقدام")), variable=self.team_attention_only,
                        command=self.fill_team).pack(side=side, padx=4)
        cols = ("role", "account", "chat", "tasks", "stage", "attention", "ready")
        self.team_tree = ttk.Treeview(team, columns=cols, show="tree headings", style="WS.Treeview", height=6)
        heads = {"#0": ("Agent", "Agent"), "role": ("Role", "نقش"), "account": ("Account profile", "پروفایل اکانت"),
                 "chat": ("Chat", "چت"), "tasks": ("Open tasks", "Taskهای باز"), "stage": ("Current step", "گام فعلی"),
                 "attention": ("Needs you", "نیاز به شما"), "ready": ("Ready?", "آماده؟")}
        for col, pair in heads.items():
            self.team_tree.heading(col, text=self.wc.tr(pair))
        self.team_tree.column("#0", width=180)
        for col, wdt in (("role", 110), ("account", 130), ("chat", 110), ("tasks", 70), ("stage", 200), ("attention", 80),
                         ("ready", 100)):
            self.team_tree.column(col, width=wdt, stretch=col in ("account", "chat"))
        self.team_tree.pack(fill="both", expand=True, pady=4)
        self.fill_team()
        self.team_tree.bind("<<TreeviewSelect>>", lambda _e: self._select_from(self.team_tree, "agent"))
        pm = ttk.Frame(team, style="WS.TFrame")
        pm.pack(fill="x")
        ts = self.wc.team_settings()
        ttk.Label(pm, text=self.wc.tr(("Project manager:", "مدیر پروژه:"))).pack(side=side)
        self.pm_var = tk.StringVar(value=ts["pm_agent_id"])
        pm_box = ttk.Combobox(pm, textvariable=self.pm_var, values=[a for a, _ in self.wc.pm_choices()], width=24,
                              state="readonly")
        pm_box.pack(side=side, padx=4)
        pm_box.bind("<<ComboboxSelected>>", lambda _e: self.save_team_settings())  # saved at once (no Save button)
        ttk.Label(pm, text=f"Parallel chats: {ts['max_parallel_chats']} (Agents › Parallel chats…)",
                  style="WS.Muted.TLabel").pack(side=side, padx=(12, 0))
        acc = ttk.LabelFrame(f, text=self.wc.tr(("Your account profiles (labels only — no passwords or keys)",
                                                   "پروفایل‌های اکانت شما (فقط برچسب — بدون رمز یا کلید)")), padding=6)
        acc.grid(row=3, column=0, sticky="ew", pady=6)
        self.acc_list = tk.Listbox(acc, height=4)
        self.acc_list.pack(fill="x")
        for a in self.wc.account_rows():
            state = "" if a.get("enabled", True) else " (off)"
            self.acc_list.insert("end", f"{a['account_profile_id']} · {a['display_name']} · {a['provider']} · "
                                        f"{a['plan']} (self-declared) · {a['bindings']} chat(s){state}")
        ab = ttk.Frame(acc, style="WS.TFrame")
        ab.pack(fill="x", pady=(4, 0))
        ttk.Button(ab, text=self.wc.tr(("Add account profile…", "افزودن پروفایل اکانت…")), command=self.dialog_add_account).pack(side=side)
        am = tk.Menu(ab, tearoff=False)
        am.add_command(label=self.wc.tr(("Enable / disable selected", "فعال / غیرفعال کردن انتخاب‌شده")),
                       command=self.toggle_selected_account)
        ttk.Menubutton(ab, text="More", menu=am).pack(side=side, padx=4)
        ch = self.wc.ctl.charter()
        if ch:
            cb = ttk.LabelFrame(f, text="Charter start prompts", padding=6)
            cb.grid(row=4, column=0, sticky="ew", pady=6)
            agents = sorted(ch.get("start_prompts") or {})
            self.charter_agent_var = tk.StringVar(value=agents[0] if agents else "")
            ttk.Combobox(cb, textvariable=self.charter_agent_var, values=agents, width=24, state="readonly").pack(side=side)
            ttk.Button(cb, text="Copy start prompt", command=self.copy_start_prompt).pack(side=side, padx=4)
        items = self.wc.tool_items("project")
        if items:
            tf = ttk.LabelFrame(f, text=self.wc.tr(("Files, builds and the phone", "فایل‌ها، Build و موبایل")), padding=6)
            tf.grid(row=5, column=0, sticky="ew", pady=6)
            ttk.Label(tf, text=self.wc.tr(("Answers, repairs, context requests, builds and the phone use the existing "
                                          "tools. Prepared context is NOT sent until you paste it into the chat yourself; "
                                          "builds and releases are recorded only when they really happened.",
                                          "پاسخ‌ها، اصلاح، درخواست زمینه، Build و موبایل از ابزارهای موجود استفاده "
                                          "می‌کنند. زمینهٔ آماده‌شده تا وقتی خودتان Paste نکنید ارسال نشده است.")),
                      style="WS.Muted.TLabel", wraplength=760, anchor=anchor).pack(fill="x")
            tm = tk.Menu(tf, tearoff=False)
            for key, label in items:
                tm.add_command(label=label, command=lambda k=key: self._guard(lambda: self.wc.open_tool(k)))
            self.tools_menu = tm
            mb = ttk.Menubutton(tf, text=self.wc.tr(("Project tools", "ابزارهای پروژه")), menu=tm)
            mb._aiwb_link = "tools"  # type: ignore[attr-defined]  # App Map: links to tools whose home is elsewhere
            mb.pack(side=side, pady=(4, 0))
        ttk.Label(f, text=self.wc.tr(("Ctrl+B sidebar · Ctrl+I inspector · Alt+1…3 sections. View, language and theme "
                                     "never change project data.",
                                     "Ctrl+B نوار کناری · Ctrl+I بازرس · Alt+1…3 بخش‌ها. نما، زبان و تم دادهٔ پروژه را تغییر نمی‌دهند.")),
                  style="WS.Muted.TLabel", wraplength=700).grid(row=6, column=0, sticky="w", pady=(6, 0))

    def fill_team(self) -> list[str]:
        """Team rows (registry + dashboard columns); 7–10 agents start with 'needs action only' (spec §10.4)."""
        dash = self.wc.dashboard(text=self.team_filter.get(), attention_only=self.team_attention_only.get())
        by = {a["agent_id"]: a for a in dash["agents"]}
        self.team_tree.delete(*self.team_tree.get_children())
        shown = []
        for r in self.wc.team_rows():
            d = by.get(r["agent_id"])
            if d is None:
                continue
            ok = {"bound": "✓", "no_binding": "–", "account_disabled": "⚠", "agent_disabled": "✕"}.get(r["readiness"], "?")
            self.team_tree.insert("", "end", iid=r["agent_id"], text=r["name"],
                                  values=(r["role"], r["account"] or "—", r["chat"] or "—", r["open_tasks"],
                                          d["stage_text"] or "—", ("● " + str(d["attention"])) if d["attention"] else "—",
                                          f"{ok} {r['readiness']}"))
            shown.append(r["agent_id"])
        return shown

    # -- team planner (2.4.0). 5.11.0: no buttons any more (the wizard and the charter plan the team; parallel chats
    # live in Agents › Parallel chats…, the manager in Project settings); the methods stay for scripts and tests.
    def save_team_settings(self, **override: Any) -> Any:
        ts = self.wc.team_settings()
        pm = self.pm_var.get() if hasattr(self, "pm_var") else ts["pm_agent_id"]
        changes = {"max_parallel_chats": override.get("max_parallel_chats", ts["max_parallel_chats"]),
                   "pm_agent_id": override.get("pm_agent_id", pm)}
        out = self._guard(lambda: self.wc.set_team_settings(**changes))
        if out:
            self.status_var.set(self.wc.tr(("Team settings saved.", "تنظیمات تیم ذخیره شد.")))
        return out

    def dialog_plan_team(self, project: dict[str, Any] | None = None) -> str:
        """Short form (goal required, the rest optional) → team planning prompt to copy (spec §7.2, Gate A)."""
        if project is None:
            project = self._ask_project_brief()
            if not project:
                return ""
        prompt = self._guard(lambda: self.wc.plan_team(project))
        if not prompt:
            return ""
        self.last_prompt, self.last_handoff_id = prompt, ""
        self.status_var.set(self.wc.tr(("Team planning prompt ready. Copy it to your project-manager chat (not sent yet).",
                                        "پرامپت برنامه‌ریزی تیم آماده است. آن را در چت مدیر پروژه کپی کنید (هنوز ارسال نشده).")))
        self.show("tasks")
        return prompt

    def _ask_project_brief(self) -> dict[str, Any]:
        dlg = tk.Toplevel(self.win)
        dlg.title(self.wc.tr(("Plan team & tasks", "برنامه‌ریزی تیم و Taskها")))
        dlg.transient(self.top)
        fields = (("goal", ("Goal (required)", "هدف (الزامی)")), ("non_goals", ("Not in scope", "خارج از دامنه")),
                  ("success", ("Success criteria", "معیار موفقیت")), ("platform", ("Platform / technology", "پلتفرم / فناوری")),
                  ("constraints", ("Constraints", "محدودیت‌ها")), ("limits", ("Time / cost limits", "محدودیت زمان / هزینه")))
        vars_: dict[str, tk.StringVar] = {}
        for i, (k, pair) in enumerate(fields):
            ttk.Label(dlg, text=self.wc.tr(pair)).grid(row=i, column=0, sticky="w", padx=6, pady=2)
            vars_[k] = tk.StringVar(value=str(self.wc.ctl.state()["settings"].get("goal", "")) if k == "goal" else "")
            ttk.Entry(dlg, textvariable=vars_[k], width=60).grid(row=i, column=1, sticky="ew", padx=6, pady=2)
        out: dict[str, Any] = {}

        def ok() -> None:
            out.update({k: v.get().strip() for k, v in vars_.items() if v.get().strip()})
            dlg.destroy()
        ttk.Button(dlg, text="OK", command=ok).grid(row=len(fields), column=1, sticky="e", padx=6, pady=6)
        dlg.grab_set()
        self.win.wait_window(dlg)
        return out

    def toggle_selected_account(self) -> Any:
        sel = self.acc_list.curselection() if hasattr(self, "acc_list") else ()
        if not sel:
            self.status_var.set(self.wc.tr(("Select an account profile first.", "ابتدا یک پروفایل اکانت انتخاب کنید.")))
            return None
        acc = self.wc.account_rows()[sel[0]]
        out = self._guard(lambda: self.wc.set_account_enabled(acc["account_profile_id"], not acc.get("enabled", True)))
        self.show("project")
        return out

    # -- proposal review (2.4.0, spec §7.5)
    def _proposal_review(self, f: ttk.Frame, row: int) -> None:
        pending = self.wc.pending_proposals()
        self.review_pid = ""
        if not pending:
            return
        pid = pending[-1]["proposal_id"]
        self.review_pid = pid
        v = self.wc.proposal_review(pid)
        box = ttk.LabelFrame(f, text=self.wc.tr(("Proposal to review: ", "پیشنهاد برای بازبینی: ")) + pid, padding=6)
        box.grid(row=row, column=0, sticky="nsew", pady=4)
        f.rowconfigure(row, weight=1)
        anchor = "e" if self.wc.rtl else "w"
        for line in ([v["summary"]] if v["summary"] else []) + v["head"]:
            ttk.Label(box, text=line, wraplength=760, anchor=anchor).pack(fill="x")
        for i in v["issues"]:
            sym = {"error": "✕", "warning": "⚠", "info": "ℹ"}.get(i["level"], "•")
            ttk.Label(box, text=f"{sym} {i['message']}", wraplength=760, anchor=anchor).pack(fill="x")
        self.review_tree = ttk.Treeview(box, columns=("op", "detail", "check"), show="tree headings",
                                        style="WS.Treeview", height=6, selectmode="extended")
        for c, pair, wdt in (("#0", ("Item", "مورد"), 220), ("op", ("Operation", "عملیات"), 120),
                             ("detail", ("Owner · scope · criteria", "مالک · Scope · معیار"), 300), ("check", ("Check", "بررسی"), 200)):
            self.review_tree.heading(c, text=self.wc.tr(pair))
            self.review_tree.column(c, width=wdt, stretch=c in ("#0", "detail"))
        for r in v["rows"]:
            self.review_tree.insert("", "end", iid=str(r["index"]), text=f"#{r['index'] + 1} {r['label']}",
                                    values=(r["operation"], r["detail"], "✓" if r["valid"] else "✕ " + r["problem"]))
        self.review_tree.selection_set([str(i) for i in v["valid_indices"]])
        self.review_tree.pack(fill="both", expand=True, pady=4)
        bb = ttk.Frame(box, style="WS.TFrame")
        bb.pack(fill="x")
        side = "right" if self.wc.rtl else "left"
        ttk.Button(bb, text=self.wc.tr(("Accept selected", "پذیرش موارد انتخاب‌شده")), style="WS.Primary.TButton",
                   command=lambda: self.review_accept()).pack(side=side)
        rm = tk.Menu(bb, tearoff=False)  # 5.11.0: one button + More (Plan & Tasks shows at most 8 controls)
        rm.add_command(label=self.wc.tr(("Reject all", "رد همه")), command=lambda: self.review_reject())
        rm.add_command(label=self.wc.tr(("Request changes (prompt)", "درخواست اصلاح (پرامپت)")),
                       command=lambda: self.review_request_changes())
        ttk.Menubutton(bb, text="More", menu=rm).pack(side=side, padx=4)

    def _review_selection(self) -> list[int]:
        return sorted(int(i) for i in self.review_tree.selection()) if hasattr(self, "review_tree") else []

    def review_accept(self, indices: list[int] | None = None, confirm_stale: bool | None = None) -> Any:
        pid = self.review_pid
        if not pid:
            return None
        idx = indices if indices is not None else self._review_selection()
        if not idx:
            self.status_var.set(self.wc.tr(("Select at least one item, or use Reject all.", "حداقل یک مورد انتخاب کنید یا «رد همه» را بزنید.")))
            return None
        v = self.wc.proposal_review(pid)
        if v["stale"] and confirm_stale is None:
            confirm_stale = messagebox.askyesno("AI Workbench", self.wc.tr((
                "This proposal was written for an older project state. Apply the selected items anyway?",
                "این پیشنهاد برای وضعیت قدیمی‌تر پروژه نوشته شده است. موارد انتخاب‌شده با این حال اعمال شوند؟")), parent=self.win)
            if not confirm_stale:
                return None
        pre = self._guard(lambda: self.wc.preview_proposal(pid, idx))
        if pre is None:
            return None
        if pre["errors"]:
            self.status_var.set("; ".join(pre["errors"])[:400])
            return None
        out = self._guard(lambda: self.wc.accept_proposal(pid, idx, confirm_stale=bool(confirm_stale)))
        if out:
            self.status_var.set(f"{pid}: {out['status']} · " + ", ".join(out["result"].get("created", {}).values()))
            self.show("plan")
        return out

    def review_reject(self) -> Any:
        if not self.review_pid:
            return None
        out = self._guard(lambda: self.wc.reject_proposal(self.review_pid))
        if out:
            self.status_var.set(f"{out['proposal_id']}: {out['status']}")
            self.show("plan")
        return out

    def review_request_changes(self, note: str = "") -> str:
        if not self.review_pid:
            return ""
        prompt = self._guard(lambda: self.wc.proposal_revision_prompt(self.review_pid, note)) or ""
        if prompt:
            self.last_prompt, self.last_handoff_id = prompt, ""
            self.status_var.set(self.wc.tr(("Revision request ready to copy; nothing was applied.",
                                            "درخواست اصلاح آمادهٔ کپی است؛ چیزی اعمال نشد.")))
            self.show("tasks")
        return prompt

    def show_lanes(self) -> dict[str, list[dict[str, Any]]]:
        """Replace the list with one parent row per lane (agent); children are that lane's events (oldest first)."""
        lanes = self.wc.timeline_lanes()
        self.tl_tree.delete(*self.tl_tree.get_children())
        for lane, recs in sorted(lanes.items()):
            self.tl_tree.insert("", "end", iid=f"lane:{lane}", values=(f"▸ {lane} · {len(recs)}", "", ""), open=False)
            for rec in recs[-50:]:
                self.tl_tree.insert(f"lane:{lane}", "end", iid=rec["event_id"],
                                    values=(self.wc.event_text(rec), "", rec["source"]))
        self.tl_tree.configure(show="tree headings")
        self.tl_page_var.set(self.wc.tr(("lanes", "Laneها")) + f" · {len(lanes)}")
        return lanes

    def _ask(self, title: str, prompt: str, initial: str = "") -> str:
        v = simpledialog.askstring(title, prompt, initialvalue=initial, parent=self.win)
        return (v or "").strip()

    def dialog_milestone(self, data: dict[str, Any] | None = None) -> Any:
        if data is None:
            title = self._ask(self.wc.tr(("Milestone", "Milestone")), self.wc.tr(("Milestone title:", "عنوان Milestone:")))
            if not title:
                return None
            tasks = self._ask(self.wc.tr(("Milestone", "Milestone")),
                              self.wc.tr(("Task IDs (comma separated):", "شناسهٔ Taskها (با کاما):")))
            data = {"title": title, "task_ids": [t.strip() for t in tasks.split(",") if t.strip()]}
        out = self._guard(lambda: self.wc.create_milestone(data))
        if out:
            self.status_var.set(f"{out['milestone_id']} · {out['title']}")
            self.show("timeline")
        return out

    def accept_selected_milestone(self, milestone_id: str = "", force: bool | None = None) -> Any:
        sel = milestone_id or next((i for i in self.mv_tree.selection() if i.startswith("MS-")), "")
        if not sel:
            self.status_var.set(self.wc.tr(("Select a milestone first.", "ابتدا یک Milestone انتخاب کنید.")))
            return None
        try:
            out = self.wc.accept_milestone(sel)
        except ModelError as exc:
            if force is None:
                force = messagebox.askyesno("AI Workbench", f"{exc}\n\n" + self.wc.tr((
                    "Accept anyway? This is recorded with the open tasks.", "با این حال پذیرفته شود؟ همراه Taskهای باز ثبت می‌شود.")),
                    parent=self.win)
            if not force:
                self.status_var.set(str(exc))
                return None
            out = self._guard(lambda: self.wc.accept_milestone(sel, force=True))
        if out:
            self.show("timeline")
        return out

    def dialog_version(self, data: dict[str, Any] | None = None) -> Any:
        if data is None:
            label = self._ask(self.wc.tr(("Version", "نسخه")), self.wc.tr(("Version label (e.g. 1.2.0):", "برچسب نسخه (مثلاً 1.2.0):")))
            if not label:
                return None
            data = {"label": label}
        out = self._guard(lambda: self.wc.propose_version(data))
        if out:
            self.status_var.set(f"{out['version_id']} · {out['label']} · " + self.wc.tr(("proposed (not released)", "پیشنهادی (منتشر نشده)")))
            self.show("timeline")
        return out

    def dialog_advance_version(self, version_id: str = "", status: str = "", facts: dict[str, str] | None = None) -> Any:
        vid = version_id or next((i for i in self.mv_tree.selection() if i.startswith("VER-")), "")
        if not vid:
            self.status_var.set(self.wc.tr(("Select a version first.", "ابتدا یک نسخه انتخاب کنید.")))
            return None
        if not status:
            status = self._ask(self.wc.tr(("Version", "نسخه")), self.wc.tr((
                "New status: local, tagged, released or withdrawn", "وضعیت جدید: local، tagged، released یا withdrawn")))
            if not status:
                return None
        if facts is None:
            facts = {}
            need = {"local": ("commit_sha",), "tagged": ("commit_sha", "tag"), "released": ("run_id", "artifact_sha256")}
            cur = next((v for v in self.wc.version_rows() if v["version_id"] == vid), {})
            for k in need.get(status, ()):
                facts[k] = self._ask(vid, f"{k}:", cur.get(k, ""))
        out = self._guard(lambda: self.wc.advance_version(vid, status, **facts))
        if out:
            self.status_var.set(f"{vid} → {out['status']}")
            self.show("timeline")
        return out

    def _fill_timeline(self, page: int) -> dict[str, Any]:
        page = max(page, 0)
        fam = self.tl_family.get()
        res = self.wc.timeline_page(page, families=[fam] if fam else [], text=self.tl_text.get())
        if res["pages"] and page >= res["pages"]:
            return self._fill_timeline(res["pages"] - 1)
        self.tl_page = page
        self.tl_tree.delete(*self.tl_tree.get_children())
        for rec in res["items"]:
            refs = rec.get("refs", {})
            ref = next(iter(refs.values()), "") if refs else ""
            self.tl_tree.insert("", "end", iid=rec["event_id"], values=(self.wc.event_text(rec), ref if isinstance(ref, str) else "", rec["source"]))
        self.tl_page_var.set(f"{page + 1}/{max(res['pages'], 1)} · {res['total']}")
        return res

    def select_timeline_event(self, event_id: str) -> None:
        """Canvas click → Inspector (and the same row in the event list when it is on this page)."""
        self.wc.select("event", event_id)
        if hasattr(self, "tl_tree") and self.tl_tree.winfo_exists() and self.tl_tree.exists(event_id):
            self.tl_tree.see(event_id)
        self._render_inspector()

    def _select_from(self, tree: ttk.Treeview, kind: str) -> None:
        sel = tree.selection()
        if sel:
            self.wc.select(kind, sel[0])
            self._render_inspector()

    # -- actions
    def do_plan(self, goal: str | None = None) -> str:
        goal = goal if goal is not None else simpledialog.askstring(
            self.wc.tr(("Project goal", "هدف پروژه")), self.wc.tr(("What should this project achieve?", "این پروژه باید به چه برسد؟")),
            parent=self.win)
        if not goal:
            return ""
        self.last_prompt = self.wc.ctl.planning_prompt(goal)
        self.last_handoff_id = ""
        self.status_var.set(self.wc.tr(("Planning prompt ready. Copy it to your project-manager chat (not sent yet).",
                                        "پرامپت برنامه‌ریزی آماده است. آن را در چت مدیر پروژه کپی کنید (هنوز ارسال نشده).")))
        self.show("tasks")
        return self.last_prompt

    def do_copy(self) -> str:
        text = self.prompt_text.get("1.0", "end-1c") if hasattr(self, "prompt_text") else self.last_prompt
        if not text.strip():
            self.status_var.set(self.wc.tr(("There is no prompt to copy yet.", "هنوز پرامپتی برای کپی وجود ندارد.")))
            return ""
        from ..v2.handoff import with_answer_rule
        text = with_answer_rule(text)   # 5.12.0 (B1): the answer comes back in one code block
        self.clipboard(text)
        if self.last_handoff_id:
            self._guard(lambda: self.wc.ctl.mark_copied(self.last_handoff_id))
        self.status_var.set(self.wc.tr(("Copied to the clipboard — this does not mean it was sent.",
                                        "در کلیپ‌بورد کپی شد — این به معنی ارسال نیست.")))
        return text

    def dialog_charter(self, project: dict[str, Any] | None = None) -> str:
        """Project Charter (3.4.0): short brief → the 'design the whole project' prompt to copy."""
        if project is None:
            project = self._ask_project_brief()
            if not project:
                return ""
        prompt = self._guard(lambda: self.wc.ctl.charter_prompt(project))
        if not prompt:
            return ""
        self.last_prompt, self.last_handoff_id = prompt, ""
        self.status_var.set("Project Charter prompt ready. Copy it to your project-manager chat, then paste the whole "
                            "answer back here (not sent yet).")
        self.show("tasks")
        return prompt

    def copy_start_prompt(self, agent_id: str = "") -> str:
        agent_id = agent_id or (self.charter_agent_var.get() if hasattr(self, "charter_agent_var") else "")
        prompt = self._guard(lambda: self.wc.ctl.charter_start_prompt(agent_id))
        if not prompt:
            return ""
        from ..v2.handoff import with_answer_rule
        prompt = with_answer_rule(prompt)
        self.last_prompt, self.last_handoff_id = prompt, ""
        self.clipboard(prompt)
        self.status_var.set(f"Start prompt for {agent_id} copied — paste it into that AI's own new chat.")
        return prompt

    def do_import(self, text: str | None = None) -> Any:
        raw = text if text is not None else self.answer_text.get("1.0", "end-1c")
        r = self.wc.ctl.route_answer(raw)
        self.status_var.set(r.message)
        if r.kind == "charter_rejected":
            self.last_prompt, self.last_handoff_id = r.record.get("fix_prompt", ""), ""
            self.show("tasks")
            return r
        # proposals are reviewed in Plan & Tasks; context requests go to Project settings (its tools)
        self.show({"proposal": "plan", "context_request": "project"}.get(r.kind, self.wc.section))
        return r

    def dialog_add_account(self, data: dict[str, Any] | None = None) -> Any:
        if data is None:
            name = simpledialog.askstring(self.wc.tr(("Account profile", "پروفایل اکانت")),
                                          self.wc.tr(("Name for this account (a label, e.g. “GPT paid — work”). "
                                                      "Never enter a password or key.",
                                                      "نام این اکانت (فقط برچسب، مثل «GPT پولی — کار»). هرگز رمز یا کلید وارد نکنید.")),
                                          parent=self.win)
            if not name:
                return None
            data = {"display_name": name, "provider": "Other", "plan": "unknown"}
        out = self._guard(lambda: self.wc.add_account(data))
        if out:
            self.status_var.set(f"{out['account_profile_id']} · {out['display_name']}")
            self.show("project")
        return out

    def dialog_bind_chat(self, agent_id: str, account_id: str | None = None, chat_name: str | None = None) -> Any:
        accounts = [a for a in self.wc.account_rows() if a.get("enabled", True)]
        if not accounts:
            messagebox.showinfo("AI Workbench", self.wc.tr(("Add an account profile first.", "ابتدا یک پروفایل اکانت اضافه کنید.")),
                                parent=self.win)
            return None
        if account_id is None:
            names = ", ".join(f"{a['account_profile_id']}={a['display_name']}" for a in accounts)
            account_id = simpledialog.askstring("AI Workbench", f"{names}\nID:", parent=self.win) or ""
        if chat_name is None:
            chat_name = simpledialog.askstring("AI Workbench", self.wc.tr(("Chat name (optional note)", "نام چت (یادداشت اختیاری)")),
                                               parent=self.win) or ""
        out = self._guard(lambda: self.wc.bind_chat(agent_id, account_id.strip(), chat_name))
        if out:
            self.show("project")
        return out

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
