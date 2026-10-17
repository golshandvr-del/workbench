"""Tk window for the v1.14.5 Safe Git Review & Sync Plan.

Thin adapter over :class:`aiwb.git.sync.GitSyncService`. All Git decisions
live in the service; this module only renders state and asks for consent.
Long operations run on a worker thread and report back via ``after``.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, Sequence

from . import sync as gs

_STATE_TEXT = {
    gs.CLEAN: "Clean · up to date",
    gs.LOCAL_AHEAD: "Local ahead",
    gs.REMOTE_AHEAD: "Remote ahead",
    gs.DIVERGED: "Diverged",
    gs.DIRTY: "Local changes",
    gs.CONFLICT: "Conflict",
    gs.NO_UPSTREAM: "No upstream",
    gs.DETACHED: "Detached HEAD",
}


class GitReviewDialog:
    def __init__(
        self,
        parent: tk.Misc,
        git_root: Path,
        project_subpath: str,
        service: gs.GitSyncService,
        *,
        in_scope: Callable[[str], bool],
        context_ids: dict[str, str] | None = None,
        on_changed: Callable[[], None] | None = None,
        redact: Callable[[str], str] = lambda s: s,
    ) -> None:
        self.root_path = git_root
        self.subpath = project_subpath
        self.svc = service
        self.in_scope = in_scope
        self.ids = dict(context_ids or {})
        self.on_changed = on_changed
        self.redact = redact
        self.snapshot: gs.ReviewSnapshot | None = None
        self.plan: gs.SyncPlan | None = None
        self.busy = False
        self.checked: set[str] = set()

        self.win = tk.Toplevel(parent)
        self.win.title(f"Git Review & Sync — {git_root.name}" + ("" if project_subpath == "." else f" / {project_subpath}"))
        self.win.geometry("1180x760")
        self.win.transient(parent)
        self._build()
        self.refresh(fetch=False)

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        top = ttk.Frame(self.win, padding=8)
        top.pack(fill="x")
        self.plan_var = tk.StringVar(value="Reading repository state…")
        self.branch_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.branch_var, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(top, textvariable=self.plan_var, wraplength=1120, justify="left").pack(anchor="w", pady=(2, 0))
        self.warn_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.warn_var, foreground="#B54708", wraplength=1120, justify="left").pack(anchor="w")

        bar = ttk.Frame(self.win, padding=(8, 0))
        bar.pack(fill="x")
        self.btn_fetch = ttk.Button(bar, text="Fetch + build Sync Plan", command=lambda: self.refresh(fetch=True))
        self.btn_fetch.pack(side="left")
        self.btn_refresh = ttk.Button(bar, text="Refresh (no network)", command=lambda: self.refresh(fetch=False))
        self.btn_refresh.pack(side="left", padx=(6, 0))
        self.btn_ff = ttk.Button(bar, text="Fast-forward only", command=self._fast_forward)
        self.btn_ff.pack(side="left", padx=(18, 0))
        self.btn_commit = ttk.Button(bar, text="Commit selected…", command=lambda: self._commit(push=False))
        self.btn_commit.pack(side="left", padx=(6, 0))
        self.btn_commit_push = ttk.Button(bar, text="Commit selected + Push…", command=lambda: self._commit(push=True))
        self.btn_commit_push.pack(side="left", padx=(6, 0))
        self.btn_push = ttk.Button(bar, text="Push…", command=self._push)
        self.btn_push.pack(side="left", padx=(6, 0))

        sel = ttk.Frame(self.win, padding=(8, 6, 8, 0))
        sel.pack(fill="x")
        ttk.Label(sel, text="Select:").pack(side="left")
        for label, mode in (("in-scope", "scope"), ("none", "none"), ("all", "all")):
            ttk.Button(sel, text=label, command=lambda m=mode: self._select(m)).pack(side="left", padx=(4, 0))
        self.counts_var = tk.StringVar(value="")
        ttk.Label(sel, textvariable=self.counts_var, foreground="#475467").pack(side="left", padx=(14, 0))

        body = ttk.PanedWindow(self.win, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=8)
        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=1)
        self.tree = ttk.Treeview(left, columns=("sel", "state", "scope"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Path")
        self.tree.heading("sel", text="Commit")
        self.tree.heading("state", text="State")
        self.tree.heading("scope", text="Scope")
        self.tree.column("#0", width=380, stretch=True)
        self.tree.column("sel", width=60, anchor="center", stretch=False)
        self.tree.column("state", width=150, anchor="w", stretch=False)
        self.tree.column("scope", width=80, anchor="center", stretch=False)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._show_diff)
        self.tree.bind("<Double-1>", self._toggle)
        self.tree.bind("<space>", self._toggle)
        self.diff = tk.Text(right, wrap="none", font=("Consolas", 9))
        self.diff.pack(fill="both", expand=True)
        self.diff.configure(state="disabled")

        bottom = ttk.Frame(self.win, padding=(8, 0, 8, 8))
        bottom.pack(fill="x")
        ttk.Label(bottom, text="Double-click / Space toggles a file. Already-staged files that you did not select block the commit. "
                               "Secret scanning is best-effort, not a guarantee. No merge, rebase or force push is ever run automatically.",
                  foreground="#667085", wraplength=1120).pack(anchor="w")

    # ---------------------------------------------------------------- worker
    def _run(self, label: str, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_buttons()
        self.plan_var.set(label)

        # Tk is not thread-safe: the worker only puts its result on a queue and
        # the Tk thread polls it with after() (same pattern as the main window).
        results: queue.Queue = queue.Queue(maxsize=1)

        def runner() -> None:
            try:
                results.put((work(), None))
            except Exception as exc:  # surfaced to the user below
                results.put((None, exc))

        def poll() -> None:
            try:
                result, error = results.get_nowait()
            except queue.Empty:
                try:
                    self.win.after(50, poll)
                except tk.TclError:
                    pass
                return
            try:
                self._finish(done, result, error)
            except tk.TclError:
                pass  # window closed while the operation was running

        threading.Thread(target=runner, name="AIWorkbenchGitReview", daemon=True).start()
        self.win.after(50, poll)

    def _finish(self, done: Callable[[Any], None], result: Any, error: Exception | None) -> None:
        self.busy = False
        if error is not None:
            self.plan_var.set("Operation failed: " + self.redact(str(error)))
            self._set_buttons()
            messagebox.showerror("Git operation failed", self.redact(str(error)), parent=self.win)
            return
        done(result)

    # ---------------------------------------------------------------- refresh
    def refresh(self, *, fetch: bool) -> None:
        def work() -> tuple[gs.ReviewSnapshot, gs.SyncPlan]:
            plan = self.svc.build_plan(self.root_path, fetch=fetch)
            return self.svc.review_snapshot(self.root_path), plan

        self._run("Fetching and building Sync Plan…" if fetch else "Reading local status…", work, self._render)

    def _render(self, result: tuple[gs.ReviewSnapshot, gs.SyncPlan]) -> None:
        self.snapshot, self.plan = result
        snap, plan = result
        b = snap.branch
        self.branch_var.set(f"Branch: {b.branch or '(detached)'}  ·  upstream: {b.upstream or '(none)'}  ·  "
                            f"HEAD {b.head_sha[:12] or '(unborn)'}  ·  ahead {b.ahead} / behind {b.behind}")
        text = f"Sync Plan: {_STATE_TEXT.get(plan.state, plan.state)} — {plan.summary}"
        if plan.manual_options:
            text += "\nManual options:\n  • " + "\n  • ".join(plan.manual_options)
        if not plan.fetched and not plan.fetch_error:
            text += "\n(Remote state not fetched in this view; use 'Fetch + build Sync Plan' before syncing.)"
        self.plan_var.set(text)
        warnings = list(plan.warnings)
        if plan.fetch_error:
            warnings.append("Fetch error: " + self.redact(plan.fetch_error))
        self.warn_var.set("\n".join(warnings))
        live = {e.path for e in snap.entries if e.kind != "ignored"}
        if not self.checked:
            self.checked = {e.path for e in snap.entries if self._selectable(e) and self.in_scope(e.path)}
        else:
            self.checked &= live
        self.tree.delete(*self.tree.get_children())
        for e in snap.entries:
            if e.kind == "ignored":
                continue
            label = ", ".join(e.labels())
            if e.renamed and e.orig_path:
                label += f" (from {e.orig_path})"
            self.tree.insert("", "end", iid=e.path, text=e.path,
                             values=("☑" if e.path in self.checked else "☐", label, "in" if self.in_scope(e.path) else "OUT"))
        c = snap.counts()
        self.counts_var.set(" · ".join(f"{k} {v}" for k, v in c.items()) + f"  ·  selected {len(self.checked)}")
        self._set_buttons()

    @staticmethod
    def _selectable(e: gs.ReviewEntry) -> bool:
        return e.kind in ("changed", "renamed", "untracked")

    def _set_buttons(self) -> None:
        plan = self.plan
        fetched = bool(plan and plan.fetched)
        state = lambda ok: "normal" if (ok and not self.busy) else "disabled"
        has_sel = bool(self.checked)
        commit_ok = bool(plan and "commit_selected" in plan.allowed_actions and has_sel)
        self.btn_fetch.configure(state=state(True))
        self.btn_refresh.configure(state=state(True))
        self.btn_ff.configure(state=state(bool(plan and plan.can_fast_forward and fetched)))
        self.btn_commit.configure(state=state(commit_ok))
        push_possible = bool(plan and fetched and plan.branch.casefold() not in gs.PROTECTED_BRANCHES
                             and plan.state in (gs.DIRTY, gs.LOCAL_AHEAD, gs.NO_UPSTREAM, gs.CLEAN))
        self.btn_commit_push.configure(state=state(commit_ok and push_possible))
        self.btn_push.configure(state=state(bool(plan and plan.can_push and fetched)))

    # ---------------------------------------------------------------- selection / diff
    def _select(self, mode: str) -> None:
        if not self.snapshot:
            return
        entries = [e for e in self.snapshot.entries if self._selectable(e)]
        if mode == "none":
            self.checked = set()
        elif mode == "all":
            self.checked = {e.path for e in entries}
        else:
            self.checked = {e.path for e in entries if self.in_scope(e.path)}
        self._render((self.snapshot, self.plan))

    def _toggle(self, _event: Any = None) -> None:
        iid = self.tree.focus()
        if not iid or not self.snapshot:
            return
        entry = next((e for e in self.snapshot.entries if e.path == iid), None)
        if entry is None or not self._selectable(entry):
            return
        self.checked.symmetric_difference_update({iid})
        self._render((self.snapshot, self.plan))
        self.tree.focus(iid)
        self.tree.selection_set(iid)

    def _show_diff(self, _event: Any = None) -> None:
        iid = self.tree.focus()
        if not iid or not self.snapshot:
            return
        entry = next((e for e in self.snapshot.entries if e.path == iid), None)
        if entry is None:
            return
        try:
            text = self.redact(self.svc.file_diff(self.root_path, entry))
        except Exception as exc:
            text = f"(diff unavailable: {self.redact(str(exc))})"
        self.diff.configure(state="normal")
        self.diff.delete("1.0", "end")
        self.diff.insert("1.0", text)
        self.diff.configure(state="disabled")

    # ---------------------------------------------------------------- actions
    def _fast_forward(self) -> None:
        plan = self.plan
        if not plan or not messagebox.askyesno("Fast-forward", f"Update '{plan.branch}' to {plan.upstream} with a fast-forward-only merge?\n"
                                               f"{plan.behind} incoming commit(s). Local files are not overwritten; Git refuses if they would be.",
                                               parent=self.win):
            return
        self._run("Fast-forwarding…", lambda: self.svc.fast_forward(self.root_path, plan), self._after_op)

    def _ask_message(self, paths: Sequence[str]) -> str | None:
        dlg = tk.Toplevel(self.win)
        dlg.title("Commit message")
        dlg.transient(self.win)
        dlg.grab_set()
        ttk.Label(dlg, text=f"{len(paths)} selected file(s). Edit the message; Workbench trailers are added below it. "
                            "The prompt is never stored in the commit.", wraplength=620).pack(anchor="w", padx=10, pady=(10, 4))
        txt = tk.Text(dlg, width=80, height=6)
        txt.pack(fill="both", expand=True, padx=10)
        txt.insert("1.0", self.ids.get("summary") or "workbench: save reviewed project changes")
        fields: dict[str, tk.StringVar] = {}
        grid = ttk.Frame(dlg)
        grid.pack(fill="x", padx=10, pady=6)
        for row, (key, label) in enumerate((("task_id", "Task ID"), ("run_id", "Run ID"), ("apply_id", "Apply ID"))):
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=self.ids.get(key, ""))
            ttk.Entry(grid, textvariable=var, width=50).grid(row=row, column=1, sticky="w", padx=6, pady=1)
            fields[key] = var
        listing = tk.Text(dlg, width=80, height=8)
        listing.pack(fill="both", padx=10)
        listing.insert("1.0", "\n".join(paths[:200]) + ("\n…" if len(paths) > 200 else ""))
        listing.configure(state="disabled")
        out: dict[str, str] = {}

        def ok() -> None:
            try:
                out["msg"] = gs.build_commit_message(txt.get("1.0", "end"), **{k: v.get() for k, v in fields.items()})
            except Exception as exc:
                messagebox.showerror("Invalid commit message", str(exc), parent=dlg)
                return
            dlg.destroy()

        btns = ttk.Frame(dlg)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="right")
        ttk.Button(btns, text="OK", command=ok).pack(side="right", padx=6)
        self.win.wait_window(dlg)
        return out.get("msg")

    def _commit(self, *, push: bool) -> None:
        if not self.snapshot or not self.plan or not self.checked:
            return
        paths = sorted(self.checked)
        outside = [p for p in paths if not self.in_scope(p)]
        if outside and not messagebox.askyesno(
                "Outside active project", f"{len(outside)} selected path(s) are OUTSIDE the active project scope "
                f"({self.subpath}):\n\n" + "\n".join(outside[:15]) + "\n\nInclude them anyway?", icon="warning", parent=self.win):
            return
        message = self._ask_message(paths)
        if not message:
            return
        plan = self.plan
        if push:
            work = lambda: self.svc.commit_and_push(self.root_path, paths, message, plan)
        else:
            work = lambda: self.svc.commit_selected(self.root_path, paths, message)
        self._run("Committing selected files…", work, self._after_op)

    def _push(self) -> None:
        plan = self.plan
        if not plan:
            return
        if not messagebox.askyesno("Push", f"Push '{plan.branch}' to origin?\n\nThe remote branch SHA is re-checked first; "
                                   "if it changed since this plan, nothing is pushed. No force push.", parent=self.win):
            return
        self._run("Verifying remote and pushing…", lambda: self.svc.safe_push(self.root_path, plan), self._after_op)

    def _after_op(self, result: gs.OperationResult) -> None:
        text = self.redact(result.message)
        if result.details:
            text += "\n\n" + "\n".join(self.redact(d) for d in result.details[:30])
        if result.ok:
            messagebox.showinfo("Done", text, parent=self.win)
        elif result.commit_created:
            messagebox.showwarning("Commit created, push failed", text, parent=self.win)
        else:
            messagebox.showerror(f"{result.stage.replace('_', ' ').title()} not completed", text, parent=self.win)
        if result.ok or result.commit_created:
            self.checked = set()
        if self.on_changed:
            try:
                self.on_changed()
            except Exception:
                pass
        self.refresh(fetch=False)
