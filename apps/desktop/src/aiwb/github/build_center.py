"""Tk Build Center window (roadmap v1.14.6): Workflow & Run monitoring.

Thin adapter over :class:`aiwb.github.actions.GitHubActionsService`. Network
calls run on a worker thread and report through a queue polled on the Tk
thread (Tk is not thread-safe). Polling follows :class:`PollPolicy`, so the
window stays responsive and respects GitHub rate limits.

1.14.6 scope: observe only. No dispatch, no artifact download, no push. The
only write action is *Cancel Run*, which needs Actions write permission and an
explicit confirmation.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Any, Callable

from . import actions as ga

_OUTCOME_TEXT = {
    "success": "✔ success", "failure": "✖ failure", "cancelled": "⊘ cancelled", "skipped": "↷ skipped",
    "timed_out": "⏱ timed out", "action_required": "! action required", "neutral": "· neutral",
    "stale": "· stale", "startup_failure": "✖ startup failure", "running": "▶ running",
    "queued": "… queued", "waiting": "… waiting", "requested": "… requested", "pending": "… pending",
    "completed_unknown": "? completed", "unknown": "?",
}
_DISPATCH_TEXT = {"available": "yes", "not_available": "no", "unknown": "unknown"}
_BINDING_TEXT = {
    "unset": "No main Build workflow is selected for this project.",
    "ok": "",
    "disabled": "The selected Build workflow is disabled on GitHub.",
    "stale": "The selected Build workflow no longer exists (renamed or deleted). Choose it again.",
}


def _short_time(value: str) -> str:
    return value.replace("T", " ").replace("Z", "")[:16] if value else ""


class BuildCenterWindow:
    def __init__(
        self,
        parent: tk.Misc,
        *,
        owner: str,
        repo: str,
        branch: str,
        get_token: Callable[[], str],
        service: ga.GitHubActionsService,
        workflow_file: str | None = None,
        local_head_sha: Callable[[], str | None] = lambda: None,
        on_select_workflow: Callable[[str], None] | None = None,
        redact: Callable[[object], str] = str,
        policy: ga.PollPolicy | None = None,
        open_url: Callable[[str], Any] = webbrowser.open,
    ) -> None:
        self.owner, self.repo, self.branch = owner, repo, branch
        self.get_token = get_token
        self.svc = service
        self.workflow_file = workflow_file
        self.local_head_sha = local_head_sha
        self.on_select_workflow = on_select_workflow
        self.redact = redact
        self.policy = policy or ga.PollPolicy()
        self.open_url = open_url
        self.workflows: tuple[ga.WorkflowInfo, ...] = ()
        self.runs: tuple[ga.WorkflowRun, ...] = ()
        self.jobs: tuple[ga.WorkflowJob, ...] = ()
        self.busy = False
        self.closed = False
        self.last_error: ga.GitHubApiError | None = None
        self._timer: str | None = None

        self.win = tk.Toplevel(parent)
        self.win.title(f"Build Center — {owner}/{repo}")
        self.win.geometry("1180x760")
        self.win.transient(parent)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self.refresh_all()

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        top = ttk.Frame(self.win, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text=f"{self.owner}/{self.repo} · branch {self.branch}", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="Loading workflows…")
        ttk.Label(top, textvariable=self.status_var, wraplength=1120, justify="left").pack(anchor="w")
        self.warn_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.warn_var, foreground="#B54708", wraplength=1120, justify="left").pack(anchor="w")
        self.correlation_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.correlation_var, foreground="#175CD3", wraplength=1120, justify="left").pack(anchor="w")

        bar = ttk.Frame(self.win, padding=(8, 0))
        bar.pack(fill="x")
        self.btn_refresh = ttk.Button(bar, text="Refresh now", command=self.refresh_all)
        self.btn_refresh.pack(side="left")
        self.btn_select = ttk.Button(bar, text="Use selected as main Build workflow", command=self._select_workflow)
        self.btn_select.pack(side="left", padx=(6, 0))
        self.only_branch = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text=f"Only runs on '{self.branch}'", variable=self.only_branch, command=self.refresh_runs).pack(side="left", padx=(18, 0))
        self.btn_open = ttk.Button(bar, text="Open run on GitHub", command=self._open_run)
        self.btn_open.pack(side="right")
        self.btn_cancel = ttk.Button(bar, text="Cancel run…", command=self._cancel_run)
        self.btn_cancel.pack(side="right", padx=(0, 6))

        panes = ttk.PanedWindow(self.win, orient="vertical")
        panes.pack(fill="both", expand=True, padx=8, pady=8)

        wf_frame = ttk.LabelFrame(panes, text="Workflows (.github/workflows)")
        self.wf_tree = ttk.Treeview(wf_frame, columns=("file", "state", "dispatch", "triggers"), height=5)
        for col, text, width in (("#0", "Name", 260), ("file", "File", 330), ("state", "State", 120), ("dispatch", "Manual run", 100), ("triggers", "Triggers", 300)):
            self.wf_tree.heading(col, text=text)
            self.wf_tree.column(col, width=width, stretch=col in {"#0", "triggers"})
        self.wf_tree.pack(fill="both", expand=True)
        self.wf_tree.bind("<<TreeviewSelect>>", lambda _e: self.refresh_runs())
        panes.add(wf_frame, weight=1)

        run_frame = ttk.LabelFrame(panes, text="Runs")
        self.run_tree = ttk.Treeview(run_frame, columns=("outcome", "branch", "sha", "event", "attempt", "created", "updated"), height=8)
        for col, text, width in (("#0", "Run", 230), ("outcome", "Result", 130), ("branch", "Branch / ref", 170), ("sha", "Commit", 90),
                                 ("event", "Event", 110), ("attempt", "Attempt", 60), ("created", "Created (UTC)", 130), ("updated", "Updated (UTC)", 130)):
            self.run_tree.heading(col, text=text)
            self.run_tree.column(col, width=width, stretch=col == "#0")
        self.run_tree.pack(fill="both", expand=True)
        self.run_tree.bind("<<TreeviewSelect>>", lambda _e: self._load_jobs())
        self.run_tree.bind("<Double-1>", lambda _e: self._open_run())
        panes.add(run_frame, weight=2)

        job_frame = ttk.LabelFrame(panes, text="Jobs and failed steps of the selected run")
        self.job_tree = ttk.Treeview(job_frame, columns=("result", "started", "completed"), height=6)
        for col, text, width in (("#0", "Job / step", 520), ("result", "Result", 140), ("started", "Started", 140), ("completed", "Completed", 140)):
            self.job_tree.heading(col, text=text)
            self.job_tree.column(col, width=width, stretch=col == "#0")
        self.job_tree.pack(fill="both", expand=True)
        self.job_tree.bind("<Double-1>", lambda _e: self._open_job())
        panes.add(job_frame, weight=1)
        self._update_buttons()

    # ---------------------------------------------------------------- worker
    def _run(self, label: str, work: Callable[[], Any], done: Callable[[Any], None], *, poll: bool = False) -> None:
        if self.busy or self.closed:
            return
        self.busy = True
        self._update_buttons()
        self.status_var.set(label + "…")
        results: queue.Queue = queue.Queue(maxsize=1)

        def runner() -> None:
            try:
                token = self.get_token()
                results.put((work(token), None))
            except Exception as exc:  # categorized below; never shown raw
                results.put((None, exc))

        def check() -> None:
            if self.closed:
                return
            try:
                result, error = results.get_nowait()
            except queue.Empty:
                self.win.after(50, check)
                return
            self.busy = False
            try:
                if error is None:
                    self.last_error = None
                    self.warn_var.set("")
                    done(result)
                else:
                    self._show_error(error)
            finally:
                self._update_buttons()
                if poll:
                    self._schedule()

        threading.Thread(target=runner, name="AIWorkbenchBuildCenter", daemon=True).start()
        self.win.after(50, check)

    def _show_error(self, error: BaseException) -> None:
        self.policy.record_error(error)
        if isinstance(error, ga.GitHubApiError):
            self.last_error = error
            hint = {
                "authentication": " Polling stopped until the credential is replaced.",
                "permission_or_policy": " The token may lack Actions: read (or Contents: read) for this repository.",
                "rate_limit": " Polling is paused until the limit resets.",
                "timeout": " Will retry with backoff.", "network": " Will retry with backoff.", "server": " Will retry with backoff.",
            }.get(error.category, "")
            self.warn_var.set(f"[{error.category}] {self.redact(error)}{hint}")
        else:
            self.warn_var.set("Unexpected error: " + self.redact(type(error).__name__))
        self.status_var.set("Last refresh failed.")

    # ---------------------------------------------------------------- polling
    def _schedule(self) -> None:
        if self.closed or self.policy.stopped:
            return
        if self._timer:
            try:
                self.win.after_cancel(self._timer)
            except tk.TclError:
                pass
        delay_ms = int(max(1.0, self.policy.next_delay()) * 1000)
        self._timer = self.win.after(delay_ms, self._tick)

    def _tick(self) -> None:
        self._timer = None
        if self.closed:
            return
        if self.busy or not self.policy.may_fetch_now():
            self._schedule()
            return
        self.refresh_runs(poll=True)

    def close(self) -> None:
        self.closed = True
        if self._timer:
            try:
                self.win.after_cancel(self._timer)
            except tk.TclError:
                pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- actions
    def refresh_all(self) -> None:
        branch = self.branch if self.only_branch.get() else None  # read Tk state on the Tk thread

        def work(token: str) -> tuple[tuple[ga.WorkflowInfo, ...], tuple[ga.WorkflowRun, ...]]:
            wfs = self.svc.list_workflows(token, self.owner, self.repo, ref=self.branch)
            wid = self._preferred_workflow_id(wfs)
            runs = self.svc.list_runs(token, self.owner, self.repo, workflow_id=wid, branch=branch)
            return wfs, runs

        def done(result: tuple[tuple[ga.WorkflowInfo, ...], tuple[ga.WorkflowRun, ...]]) -> None:
            self.workflows, runs = result
            self._render_workflows()
            self._apply_runs(runs)

        self._run("Loading workflows and runs", work, done, poll=True)

    def refresh_runs(self, poll: bool = False) -> None:
        wid = self._selected_workflow_id()
        branch = self.branch if self.only_branch.get() else None

        def work(token: str) -> tuple[ga.WorkflowRun, ...]:
            return self.svc.list_runs(token, self.owner, self.repo, workflow_id=wid, branch=branch)

        self._run("Refreshing runs", work, self._apply_runs, poll=True)

    def _apply_runs(self, runs: tuple[ga.WorkflowRun, ...]) -> None:
        selected = self._selected_run()
        self.runs = runs
        self.policy.record_success(any_running=any(not r.is_finished for r in runs))
        self.run_tree.delete(*self.run_tree.get_children())
        for r in runs:
            iid = f"{r.run_id}:{r.run_attempt or 1}"
            self.run_tree.insert("", "end", iid=iid, text=f"#{r.run_number or '?'} {r.name} (id {r.run_id})", values=(
                _OUTCOME_TEXT.get(r.outcome, r.outcome), r.head_branch, r.head_sha[:7], r.event, r.run_attempt or 1,
                _short_time(r.created_at), _short_time(r.updated_at)))
        if selected and self.run_tree.exists(f"{selected.run_id}:{selected.run_attempt or 1}"):
            self.run_tree.selection_set(f"{selected.run_id}:{selected.run_attempt or 1}")
        running = sum(1 for r in runs if not r.is_finished)
        self.status_var.set(f"{len(runs)} run(s) loaded · {running} in progress · next refresh in ~{int(self.policy.next_delay())}s")
        self._render_correlation()
        self._update_buttons()

    def _render_correlation(self) -> None:
        sha = None
        try:
            sha = self.local_head_sha()
        except Exception:
            sha = None
        if not sha or len(sha) != 40:
            self.correlation_var.set("")
            return
        corr = ga.correlate_runs_with_commit(self.runs, sha, branch=self.branch)
        if corr.state == "matched" and corr.run:
            self.correlation_var.set(f"Local HEAD {sha[:7]} → run {corr.run.run_id}: {_OUTCOME_TEXT.get(corr.run.outcome, corr.run.outcome)}")
        elif corr.state == "only_older_runs" and corr.newest_other:
            self.correlation_var.set(f"No run yet for local HEAD {sha[:7]}. The newest run on '{self.branch}' is for a different commit "
                                     f"({corr.newest_other.head_sha[:7]}) and is NOT the result of your latest changes.")
        else:
            self.correlation_var.set(f"No run found for local HEAD {sha[:7]} on '{self.branch}'.")

    def _render_workflows(self) -> None:
        self.wf_tree.delete(*self.wf_tree.get_children())
        for wf in self.workflows:
            triggers = ", ".join(wf.triggers) if wf.triggers is not None else "(could not read)"
            name = ("★ " if wf.path == self.workflow_file else "") + wf.name
            self.wf_tree.insert("", "end", iid=str(wf.workflow_id), text=name, values=(wf.path, wf.state, _DISPATCH_TEXT[wf.manual_dispatch], triggers))
        preferred = self._preferred_workflow_id(self.workflows)
        if preferred is not None and self.wf_tree.exists(str(preferred)):
            self.wf_tree.selection_set(str(preferred))
        binding_state = ga.check_workflow_binding(self.workflow_file, self.workflows)
        self.warn_var.set(_BINDING_TEXT[binding_state] if binding_state != "unset" or self.workflows else "")
        if binding_state == "unset" and self.workflows:
            self.warn_var.set(_BINDING_TEXT["unset"] + " Select one and press 'Use selected as main Build workflow'.")

    def _preferred_workflow_id(self, workflows: tuple[ga.WorkflowInfo, ...]) -> int | None:
        for wf in workflows:
            if wf.path == self.workflow_file:
                return wf.workflow_id
        return None

    def _selected_workflow_id(self) -> int | None:
        sel = self.wf_tree.selection()
        return int(sel[0]) if sel else None

    def _selected_run(self) -> ga.WorkflowRun | None:
        sel = self.run_tree.selection()
        if not sel:
            return None
        run_id, attempt = sel[0].split(":")
        return next((r for r in self.runs if r.run_id == int(run_id) and (r.run_attempt or 1) == int(attempt)), None)

    def _select_workflow(self) -> None:
        wid = self._selected_workflow_id()
        wf = next((w for w in self.workflows if w.workflow_id == wid), None)
        if wf is None:
            messagebox.showinfo("Build workflow", "Select a workflow first.", parent=self.win)
            return
        if self.on_select_workflow is None:
            return
        try:
            self.on_select_workflow(wf.path)
        except Exception as exc:
            messagebox.showerror("Build workflow", self.redact(exc), parent=self.win)
            return
        self.workflow_file = wf.path
        self._render_workflows()

    def _load_jobs(self) -> None:
        run = self._selected_run()
        self.job_tree.delete(*self.job_tree.get_children())
        self._update_buttons()
        if run is None or self.busy:
            return

        def done(jobs: tuple[ga.WorkflowJob, ...]) -> None:
            self.jobs = jobs
            self.job_tree.delete(*self.job_tree.get_children())
            for job in jobs:
                jid = f"job:{job.job_id}"
                self.job_tree.insert("", "end", iid=jid, text=job.name, open=bool(job.failed_steps),
                                     values=(job.conclusion or job.status, _short_time(job.started_at), _short_time(job.completed_at)))
                for step in job.failed_steps:
                    self.job_tree.insert(jid, "end", text=f"step {step.number}: {step.name}", values=(step.conclusion or step.status, "", ""))
            self.status_var.set(f"Run {run.run_id}: {len(jobs)} job(s), {sum(len(j.failed_steps) for j in jobs)} failed step(s). Double-click a job to open its log on GitHub.")

        self._run(f"Loading jobs of run {run.run_id}", lambda token: self.svc.list_jobs(token, self.owner, self.repo, run.run_id), done)

    def _open_run(self) -> None:
        run = self._selected_run()
        if run and run.html_url:
            self.open_url(run.html_url)

    def _open_job(self) -> None:
        sel = self.job_tree.selection()
        if not sel:
            return
        iid = sel[0] if sel[0].startswith("job:") else self.job_tree.parent(sel[0])
        job = next((j for j in self.jobs if f"job:{j.job_id}" == iid), None)
        if job and job.log_url:
            self.open_url(job.log_url)

    def _cancel_run(self) -> None:
        run = self._selected_run()
        if run is None or run.is_finished:
            return
        if not messagebox.askyesno("Cancel run", f"Request cancellation of run {run.run_id} ({run.name}) on {run.head_branch} @ {run.head_sha[:7]}?\n\n"
                                   "This needs Actions: write permission on the token.", parent=self.win):
            return

        def done(result: str) -> None:
            self.status_var.set(f"Cancellation of run {run.run_id} {result}. GitHub may take a few seconds to stop it.")
            self.policy.record_success(any_running=True)

        self._run(f"Cancelling run {run.run_id}", lambda token: self.svc.cancel_run(token, self.owner, self.repo, run, confirmed=True), done)

    def _update_buttons(self) -> None:
        run = self._selected_run() if hasattr(self, "run_tree") else None
        state = "disabled" if self.busy else "normal"
        self.btn_refresh.configure(state=state)
        self.btn_select.configure(state="normal" if (not self.busy and self.on_select_workflow) else "disabled")
        self.btn_open.configure(state="normal" if run and run.html_url else "disabled")
        self.btn_cancel.configure(state="normal" if (run and not run.is_finished and not self.busy) else "disabled")
