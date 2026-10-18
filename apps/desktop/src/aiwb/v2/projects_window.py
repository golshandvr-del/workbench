"""Tk window "Projects (multi-agent)" — Simple and Advanced views of one ProjectsController.

Simple: goal, next action, one prompt button, Copy, one paste box, plain result,
task list with words + symbols, required decisions/warnings.
Advanced: the same plus revisions, attempts, handoffs, evidence, proposals and
publisher state. Both call exactly the same controller methods (spec §19/§28).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

from .. import i18n
from .controller import ProjectsController
from .models import ModelError


class ProjectsWindow:
    def __init__(self, parent: tk.Misc, ctl: ProjectsController, *, clipboard: Callable[[str], None]) -> None:
        self.ctl = ctl
        self.clipboard = clipboard
        self.last_prompt = ""
        self.last_handoff_id = ""
        self.last_route: Any = None
        self.win = tk.Toplevel(parent)
        self.win.title("Projects (multi-agent) — AI Workbench")
        self.win.geometry("1120x760")
        top = ttk.Frame(self.win, padding=(10, 8))
        top.pack(fill="x")
        self.view_label = ttk.Label(top, text=ctl.t("view") + ":")
        self.view_label.pack(side="left")
        self.mode_var = tk.StringVar(value=ctl.mode)
        self.mode_buttons = {}
        for m in ("simple", "advanced"):
            rb = ttk.Radiobutton(top, text=ctl.t(m), value=m, variable=self.mode_var, command=self._mode_changed)
            rb.pack(side="left", padx=4)
            self.mode_buttons[m] = rb
        self.lang_var = tk.StringVar(value=ctl.lang)
        self.lang_label = ttk.Label(top, text=ctl.t("language") + ":")
        self.lang_label.pack(side="left", padx=(16, 0))
        lang_box = ttk.Combobox(top, textvariable=self.lang_var, values=list(i18n.LANGUAGES), width=4, state="readonly")
        lang_box.pack(side="left", padx=4)
        lang_box.bind("<<ComboboxSelected>>", lambda _e: self._lang_changed())
        ttk.Button(top, text="Close", command=self.close).pack(side="right")
        ttk.Button(top, text="Publish state now", command=self.do_publish).pack(side="right", padx=6)
        self.next_var = tk.StringVar()
        nxt = ttk.LabelFrame(self.win, text=ctl.t("next_step"), padding=8)
        self.next_frame = nxt
        nxt.pack(fill="x", padx=10)
        ttk.Label(nxt, textvariable=self.next_var, wraplength=1060, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.pub_var = tk.StringVar()
        ttk.Label(nxt, textvariable=self.pub_var).pack(anchor="w")
        self.warn_var = tk.StringVar()
        ttk.Label(nxt, textvariable=self.warn_var, wraplength=1060, foreground="#8a1c1c").pack(anchor="w", pady=(4, 0))
        body = ttk.Panedwindow(self.win, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=8)
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=1)
        self.tree = ttk.Treeview(left, columns=("status", "owner", "extra"), show="tree headings", height=14)
        self.tree.heading("#0", text="Task")
        self.tree.heading("status", text="Status")
        self.tree.heading("owner", text="Agent")
        self.tree.heading("extra", text="Details")
        self.tree.column("#0", width=260)
        self.tree.column("status", width=190)
        self.tree.column("owner", width=130)
        self.tree.column("extra", width=160)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_task())
        tb = ttk.Frame(left)
        tb.pack(fill="x", pady=4)
        ttk.Button(tb, text="Plan project…", command=self.do_plan).pack(side="left")
        ttk.Button(tb, text="Start selected task", command=self.do_start).pack(side="left", padx=4)
        ttk.Button(tb, text="Approve review", command=lambda: self.do_review(True)).pack(side="left")
        ttk.Button(tb, text="Reject review", command=lambda: self.do_review(False)).pack(side="left", padx=4)
        ttk.Button(tb, text="Manager update", command=self.do_manager_update).pack(side="left")
        self.detail = tk.Text(left, height=12, wrap="word")
        self.detail.pack(fill="both", expand=True)
        ttk.Label(right, text="Prompt to copy (Workbench never sends it):").pack(anchor="w")
        self.prompt_text = tk.Text(right, height=12, wrap="word")
        self.prompt_text.pack(fill="both", expand=True)
        pb = ttk.Frame(right)
        pb.pack(fill="x", pady=4)
        ttk.Button(pb, text="Copy prompt", style="Primary.TButton", command=self.do_copy).pack(side="left")
        ttk.Label(right, text="Paste the model's answer here:").pack(anchor="w", pady=(6, 0))
        self.answer = tk.Text(right, height=10, wrap="word")
        self.answer.pack(fill="both", expand=True)
        ab = ttk.Frame(right)
        ab.pack(fill="x", pady=4)
        ttk.Button(ab, text="Import answer", style="Primary.TButton", command=self.do_import).pack(side="left")
        ttk.Button(ab, text="Accept delivered work", command=lambda: self.do_resolve(True)).pack(side="left", padx=4)
        ttk.Button(ab, text="Reject delivered work", command=lambda: self.do_resolve(False)).pack(side="left")
        ttk.Button(ab, text="Review proposal…", command=self.do_proposal).pack(side="left", padx=4)
        self.result_var = tk.StringVar()
        ttk.Label(right, textvariable=self.result_var, wraplength=520).pack(anchor="w")
        # Advanced-only panels: read-only projections of the same state (spec §19)
        self.adv = ttk.Notebook(self.win)
        self.adv_text: dict[str, tk.Text] = {}
        for name in ("Agents", "Decisions", "Evidence", "Attempts", "Proposals", "Publish"):
            frame = ttk.Frame(self.adv)
            t = tk.Text(frame, height=8, wrap="none")
            t.pack(fill="both", expand=True)
            self.adv.add(frame, text=name)
            self.adv_text[name] = t
        self.refresh()
        self._timer = self.win.after(30000, self._tick)

    def _tick(self) -> None:
        try:
            if self.ctl.tick_publisher() is not None:
                self.pub_var.set(self.ctl.publish_status()["text"])
            self._timer = self.win.after(30000, self._tick)
        except tk.TclError:
            pass

    # -- view
    def _mode_changed(self) -> None:
        self.ctl.set_mode(self.mode_var.get())
        self.refresh()

    def _lang_changed(self) -> None:
        self.ctl.set_language(self.lang_var.get())
        self.view_label.configure(text=self.ctl.t("view") + ":")
        self.lang_label.configure(text=self.ctl.t("language") + ":")
        self.next_frame.configure(text=self.ctl.t("next_step"))
        for m, rb in self.mode_buttons.items():
            rb.configure(text=self.ctl.t(m))
        self.refresh()

    def refresh(self) -> None:
        self.next_var.set(self.ctl.next_action_text())
        self.pub_var.set(self.ctl.publish_status()["text"])
        nv = self.ctl.next_action_view()
        if nv and self.ctl.mode == "advanced" and nv.get("queue"):
            self.next_var.set(self.next_var.get() + f"\n{self.ctl.t('then')}: " + " · ".join(nv["queue"]))
        if self.ctl.mode == "advanced":
            if not self.adv.winfo_ismapped():
                self.adv.pack(fill="both", expand=False, padx=10, pady=(0, 8))
            for name, text in self.ctl.advanced_panels().items():
                self._set(self.adv_text[name], text)
        elif self.adv.winfo_manager():
            self.adv.pack_forget()
        w = self.ctl.warning_items()
        # symbol + words per severity: colour never carries meaning alone (§19.3)
        self.warn_var.set("\n".join(f"{i18n.SEVERITY[x['severity']][0]} {x['text']}" for x in w[:6]))
        keep = self.selected_task()
        self.tree.delete(*self.tree.get_children())
        for r in self.ctl.task_rows():
            extra = r.get("reason", "")
            if self.ctl.mode == "advanced":
                extra = f"rev {r['revision']} · deps {r['depends_on'] or '—'}"
            self.tree.insert("", "end", iid=r["task_id"], text=f"{r['task_id']} {r['title']}",
                             values=(f"{r['symbol']} {r['status_text']}", r["owner"], extra))
        if keep and self.tree.exists(keep):
            self.tree.selection_set(keep)
        self._show_task()

    def selected_task(self) -> str:
        sel = self.tree.selection()
        return sel[0] if sel else ""

    def _show_task(self) -> None:
        tid = self.selected_task()
        self._set(self.detail, self.ctl.task_details(tid) if tid else self.ctl.status_markdown())

    @staticmethod
    def _set(widget: tk.Text, text: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def _guard(self, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except ModelError as exc:
            self.result_var.set(str(exc))
            return None
        finally:
            self.refresh()

    # -- actions (each delegates to the controller)
    def do_plan(self, goal: str | None = None) -> str:
        goal = goal if goal is not None else simpledialog.askstring("Project goal", "What should this project achieve?",
                                                                    parent=self.win)
        if not goal:
            return ""
        self.last_prompt = self.ctl.planning_prompt(goal)
        self._set(self.prompt_text, self.last_prompt)
        self.result_var.set("Planning prompt ready: copy it to your project-manager chat, then paste the answer.")
        self.refresh()
        return self.last_prompt

    def do_start(self, task_id: str = "") -> dict[str, Any] | None:
        tid = task_id or self.selected_task()
        if not tid:
            self.result_var.set("Select a task first.")
            return None
        h = self._guard(lambda: self.ctl.start_task(tid))
        if h:
            self.last_handoff_id = h["handoff_id"]
            self.last_prompt = h["prompt"]
            self._set(self.prompt_text, h["prompt"])
            self.result_var.set(f"Prompt for {h['to_agent_id']} is ready ({h['handoff_id']}). Copy it to that agent's chat.")
        return h

    def do_copy(self) -> str:
        text = self.prompt_text.get("1.0", "end-1c")
        if not text.strip():
            self.result_var.set("There is no prompt to copy yet.")
            return ""
        self.clipboard(text)
        if self.last_handoff_id:
            self._guard(lambda: self.ctl.mark_copied(self.last_handoff_id))
        self.result_var.set("Copied. Paste it into the chat, then paste the answer below.")
        return text

    def do_manager_update(self) -> str:
        self.last_prompt = self.ctl.manager_update()
        self.last_handoff_id = ""
        self._set(self.prompt_text, self.last_prompt)
        self.result_var.set("Manager update ready: copy it to the project-manager chat.")
        return self.last_prompt

    def do_import(self, text: str | None = None) -> Any:
        raw = text if text is not None else self.answer.get("1.0", "end-1c")
        r = self.ctl.route_answer(raw)
        self.last_route = r
        self.result_var.set(r.message)
        self.refresh()
        return r

    def do_resolve(self, accept: bool, handoff_id: str = "") -> Any:
        hid = handoff_id or (self.last_route.reference_id if self.last_route and self.last_route.kind == "handoff" else "")
        if not hid:
            self.result_var.set("Import an agent answer first.")
            return None
        reason = ""
        h = self.ctl.project.handoffs.get(hid) or {}
        if accept and h.get("status") in ("stale", "reconciliation_required"):
            reason = simpledialog.askstring("Older answer", "This answer was made for an older task version. "
                                            "Why accept it anyway?", parent=self.win) or ""
        out = self._guard(lambda: self.ctl.resolve_handoff(hid, accept, reason))
        if out:
            self.result_var.set(f"{hid} {'accepted' if accept else 'rejected'}. Files are applied only through the "
                                "normal review → apply flow.")
        return out

    def do_review(self, approved: bool, task_id: str = "") -> Any:
        tid = task_id or self.selected_task()
        if not tid:
            self.result_var.set("Select a task first.")
            return None
        out = self._guard(lambda: self.ctl.review_task(tid, approved))
        if out:
            self.result_var.set(f"{tid}: " + ("done" if out["status"] == "done" else
                                              f"{out['status']} — " + "; ".join(out["reasons"])))
        return out

    def do_proposal(self, indices: list[int] | None = None, proposal_id: str = "") -> Any:
        pid = proposal_id or (self.last_route.reference_id if self.last_route and self.last_route.kind == "proposal" else "")
        if not pid:
            pend = self.ctl.project.proposals.list("pending")
            pid = pend[-1]["proposal_id"] if pend else ""
        if not pid:
            self.result_var.set("There is no proposal to review.")
            return None
        p = self.ctl.project.proposals.get(pid)
        if indices is None:
            indices = ProposalDialog(self.win, p).result
            if indices is None:
                return None
        confirm = bool(p.get("stale")) and (indices == [] or messagebox.askyesno(
            "Older proposal", "This proposal was written for an older project state. Apply the selected changes anyway?",
            parent=self.win, default="no"))
        out = self._guard(lambda: self.ctl.accept_proposal(pid, indices, confirm_stale=confirm))
        if out:
            res = out.get("result", {})
            self.result_var.set(f"{pid}: {out['status']}. " + " ".join(res.get("notes", [])[:3]))
        return out

    def do_publish(self) -> dict[str, Any]:
        r = self.ctl.publish_now()
        self.result_var.set("State publish: " + str(r.get("status")) + (" — " + str(r.get("message") or r.get("kind") or "")
                                                                         if r.get("status") != "published" else ""))
        self.refresh()
        return r

    def close(self) -> None:
        try:
            self.win.after_cancel(self._timer)
        except (tk.TclError, AttributeError, ValueError):
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class ProposalDialog:
    """Checkbox per operation; invalid operations cannot be selected."""

    def __init__(self, parent: tk.Misc, proposal: dict[str, Any]) -> None:
        self.result: list[int] | None = None
        self.top = tk.Toplevel(parent)
        self.top.title(f"Review {proposal['proposal_id']}")
        msg = proposal.get("summary", "")
        if proposal.get("stale"):
            msg = "⚠ Written for an older project state. " + msg
        ttk.Label(self.top, text=msg, wraplength=700).pack(anchor="w", padx=10, pady=6)
        self.vars: list[tuple[int, tk.BooleanVar]] = []
        for op in proposal["operations"]:
            v = tk.BooleanVar(value=op.get("valid", False))
            text = f"#{op['index']} {op['operation']}: {op.get('label') or op.get('raw', {}).get('title', '')}"
            if not op.get("valid"):
                text += f"  (invalid: {op.get('problem', '')})"
            cb = ttk.Checkbutton(self.top, text=text, variable=v)
            cb.pack(anchor="w", padx=14)
            if not op.get("valid"):
                cb.state(["disabled"])
            self.vars.append((op["index"], v))
        bar = ttk.Frame(self.top, padding=8)
        bar.pack(fill="x")
        ttk.Button(bar, text="Apply selected", command=self._ok).pack(side="left")
        ttk.Button(bar, text="Cancel", command=self.top.destroy).pack(side="right")
        self.top.transient(parent)
        self.top.grab_set()
        parent.wait_window(self.top)

    def _ok(self) -> None:
        self.result = [i for i, v in self.vars if v.get()]
        self.top.destroy()
