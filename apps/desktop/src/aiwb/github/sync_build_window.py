"""Tk window for the v1.14.8 One-click Sync & Build flow.

Shows the state chain, the last successful step, the real effect on Git and the
next action. All work runs on a worker thread; Tk is only touched on the Tk
thread (results come back through a queue polled with ``after``).
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from . import orchestrator as orc


class SyncBuildWindow:
    POLL_MS = 50

    def __init__(
        self, parent: tk.Misc, orchestrator: orc.SyncBuildOrchestrator, *, default_message: str = "workbench: update",
        redact: Callable[[object], str] = str, on_finished: Callable[[orc.SyncBuildOrchestrator], None] | None = None,
        ask_directory: Callable[..., str] = filedialog.askdirectory, confirm: Callable[..., bool] = messagebox.askyesno,
        ci_timeout: float = 3600, ci_interval: float = 10,
    ) -> None:
        self.orc = orchestrator
        self._dm = default_message
        self.redact = redact
        self.on_finished = on_finished
        self.ask_directory = ask_directory
        self.confirm = confirm
        self.ci_timeout, self.ci_interval = ci_timeout, ci_interval
        self.busy = False
        self.closed = False
        self._events: queue.Queue = queue.Queue()
        self.win = tk.Toplevel(parent)
        self.win.title(f"Sync & Build — {orchestrator.full_name} @ {orchestrator.branch}")
        self.win.geometry("900x620")
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        orchestrator.subscribe(lambda st, msg: self._events.put(("event", st, msg)))
        self._build()
        self._render_state()
        self.win.after(self.POLL_MS, self._pump)

    # -- layout
    def _build(self) -> None:
        top = ttk.Frame(self.win, padding=8)
        top.pack(fill="x")
        self.chain_var = tk.StringVar()
        ttk.Label(top, textvariable=self.chain_var, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.effect_var = tk.StringVar()
        ttk.Label(top, textvariable=self.effect_var).pack(anchor="w")
        self.next_var = tk.StringVar()
        ttk.Label(top, textvariable=self.next_var, foreground="#1a4f8b").pack(anchor="w")

        mid = ttk.PanedWindow(self.win, orient="vertical")
        mid.pack(fill="both", expand=True, padx=8)
        files = ttk.LabelFrame(mid, text="Changes (checked = commit; sensitive files cannot be selected)")
        self.tree = ttk.Treeview(files, columns=("sel", "path", "labels", "flags"), show="headings", height=10)
        for col, w in (("sel", 50), ("path", 420), ("labels", 160), ("flags", 200)):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, stretch=col == "path")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", self._toggle)
        self.tree.bind("<space>", self._toggle)
        mid.add(files, weight=3)
        logf = ttk.LabelFrame(mid, text="Log")
        self.log = tk.Text(logf, height=8, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)
        mid.add(logf, weight=2)

        msgf = ttk.Frame(self.win, padding=(8, 4))
        msgf.pack(fill="x")
        ttk.Label(msgf, text="Commit message:").pack(side="left")
        self.message_var = tk.StringVar(value=self._default_message_value())
        self.default_message = self.message_var.get()
        ttk.Entry(msgf, textvariable=self.message_var).pack(side="left", fill="x", expand=True, padx=6)

        bar = ttk.Frame(self.win, padding=8)
        bar.pack(fill="x")
        self.btn_check = ttk.Button(bar, text="Check", command=self.do_check)
        self.btn_check.pack(side="left")
        self.btn_go = ttk.Button(bar, text="Commit + Push + Build", command=self.do_go)
        self.btn_go.pack(side="left", padx=6)
        self.btn_download = ttk.Button(bar, text="Download & verify artifacts…", command=self.do_download)
        self.btn_download.pack(side="left")
        self.btn_cancel = ttk.Button(bar, text="Cancel", command=self.do_cancel)
        self.btn_cancel.pack(side="right")
        self.selected: set[str] = set()

    def _default_message_value(self) -> str:
        return getattr(self, "_dm", None) or "workbench: update"

    # -- helpers
    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", self.redact(text) + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _pump(self) -> None:
        if self.closed:
            return
        try:
            while True:
                item = self._events.get_nowait()
                if item[0] == "event":
                    self._append(f"[{orc.STATE_LABELS.get(item[1], item[1])}] {item[2]}")
                    self._render_state()
                elif item[0] == "done":
                    self.busy = False
                    item[1](item[2])
                    self._render_state()
                elif item[0] == "fail":
                    self.busy = False
                    self._append("Stopped: " + self.redact(item[1]))
                    self._render_state()
        except queue.Empty:
            pass
        self.win.after(self.POLL_MS, self._pump)

    def _run(self, work: Callable[[], Any], done: Callable[[Any], None] = lambda _r: None) -> None:
        if self.busy or self.closed:
            return
        self.busy = True
        self._render_state()

        def runner() -> None:
            try:
                self._events.put(("done", done, work()))
            except BaseException as exc:  # noqa: BLE001
                self._events.put(("fail", exc, None))
            finally:
                if self.closed:
                    self.orc.release()  # window closed mid-flow: free the repo lock; resumable later

        threading.Thread(target=runner, name="AIWorkbenchSyncBuild", daemon=True).start()

    def _render_state(self) -> None:
        st = self.orc.state
        chain = []
        for s in orc.CHAIN:
            label = orc.STATE_LABELS[s]
            chain.append(f"[{label}]" if s == st else label)
        extra = "" if st in orc.CHAIN else f"   ⇒ {orc.STATE_LABELS.get(st, st)}"
        self.chain_var.set(" → ".join(chain) + extra)
        last = self.orc.last_successful_step()
        self.effect_var.set(f"Last successful step: {last or '—'} · Git: {self.orc.git_effect()}")
        self.next_var.set("Next: " + self.next_action())
        g = self.orc.git
        can_go = not self.busy and self.orc.last_check is not None and self.orc.last_check.ok and st not in orc.TERMINAL \
            and st not in (orc.PREFLIGHT_FAILED, orc.STALE_PLAN) and (bool(self.selected) or bool(g.commit_sha) or not self.orc.last_check.items)
        self.btn_check.configure(state="disabled" if self.busy else "normal")
        self.btn_go.configure(state="normal" if can_go else "disabled")
        self.btn_download.configure(state="normal" if (not self.busy and st == orc.BUILD_PASSED) else "disabled")
        self.btn_cancel.configure(state="disabled" if st in orc.TERMINAL else "normal")

    def next_action(self) -> str:
        st = self.orc.state
        return {
            orc.CHECKING: "Wait for the checks.",
            orc.PREFLIGHT_FAILED: "Fix the failed checks, then press Check.",
            orc.REVIEW_REQUIRED: "Tick the files to commit, edit the message, then Commit + Push + Build.",
            orc.READY_TO_COMMIT: "Press Commit + Push + Build.",
            orc.COMMITTED: "Press Commit + Push + Build to push the recorded commit.",
            orc.PUSHING: "Pushing…",
            orc.PUSHED: "Waiting for the CI run of this commit.",
            orc.CI_QUEUED: "Waiting for the CI run of this commit.",
            orc.CI_RUNNING: "CI is running for this commit.",
            orc.BUILD_PASSED: "Download & verify artifacts.",
            orc.BUILD_FAILED: "Open the run in Build Center to see the failed steps.",
            orc.STALE_PLAN: "The remote moved: press Check to build a new plan.",
            orc.FAILED: "See the log, then press Check.",
            orc.ARTIFACT_VERIFIED: "Done: artifacts downloaded and SHA-256 matches GitHub's digest.",
            orc.ARTIFACT_DOWNLOADED: "Done: artifacts downloaded; SHA-256 computed (GitHub reported no digest for some).",
            orc.CANCELLED: "Cancelled.",
        }.get(st, "")

    # -- actions
    def _toggle(self, _e: object = None) -> None:
        for iid in self.tree.selection():
            item = self._items.get(iid)
            if item is None or item.blocked:
                continue
            if item.path in self.selected:
                self.selected.discard(item.path)
            else:
                self.selected.add(item.path)
            self.tree.set(iid, "sel", "☑" if item.path in self.selected else "☐")
        self._render_state()

    def do_check(self) -> None:
        def done(res: orc.CheckResult) -> None:
            self.tree.delete(*self.tree.get_children())
            self._items = {}
            self.selected = set()
            for item in res.items:
                preselect = not item.blocked and not item.needs_confirmation
                if preselect:
                    self.selected.add(item.path)
                iid = self.tree.insert("", "end", values=("—" if item.blocked else ("☑" if preselect else "☐"), item.path,
                                                          ", ".join(item.labels), ", ".join(item.flags)))
                self._items[iid] = item
            for c in res.checks:
                self._append(f"{'OK ' if c.ok else 'FAIL'} {c.name}: {c.detail}")
        self._items: dict[str, orc.ReviewItem] = getattr(self, "_items", {})
        self._run(self.orc.check, done)

    def do_go(self) -> None:
        paths = sorted(self.selected)
        confirm_needed = [i.path for i in getattr(self, "_items", {}).values() if i.path in self.selected and i.needs_confirmation]
        if confirm_needed and not self.confirm(
                "Sync & Build", "These files need confirmation (outside project scope or workflow changes):\n\n"
                + "\n".join(confirm_needed[:20]) + "\n\nCommit them?", parent=self.win):
            return
        message = self.message_var.get().strip() or self.default_message
        o = self.orc

        def work() -> Any:
            if not o.git.commit_sha:
                if paths:
                    o.commit(paths, message, confirmed_paths=confirm_needed)
                else:
                    o.adopt_head()
            o.push()
            return o.wait_for_build(timeout=self.ci_timeout, interval=self.ci_interval)

        def done(run: Any) -> None:
            if run is not None:
                self._append(f"Run {run.run_id}: {run.outcome} {run.html_url}")
            if self.on_finished:
                self.on_finished(o)
        self._run(work, done)

    def do_download(self) -> None:
        target = self.ask_directory(parent=self.win, title="Folder for verified artifacts")
        if not target:
            return

        def done(results: list[dict[str, Any]]) -> None:
            for r in results:
                note = "matches GitHub digest" if r["verification"] == "matched" else "computed; no reference (not verified)"
                self._append(f"{r['name']}: {r['path']} SHA-256 {r['sha256'][:16]}… ({note})")
        self._run(lambda: self.orc.download_artifacts(Path(target)), done)

    def do_cancel(self) -> None:
        o = self.orc
        if o.git.pushed and not self.confirm("Sync & Build", "Cancel the CI run of this commit? The pushed commit stays on the remote.", parent=self.win):
            return
        result = o.cancel()
        self._append("Cancel: " + result)
        self._render_state()

    def close(self) -> None:
        if self.busy and not self.confirm("Sync & Build", "An operation is running. Close the window? It can be resumed later.", parent=self.win):
            return
        self.closed = True
        self.orc.cancel_requested = True if self.busy else self.orc.cancel_requested
        if not self.busy:
            self.orc.release()
        try:
            self.win.destroy()
        except tk.TclError:
            pass
