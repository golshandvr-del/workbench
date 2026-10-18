"""Tk dialogs for Build Center (roadmap v1.14.7): manual dispatch and Artifacts.

Both are thin adapters over :mod:`aiwb.github.artifacts`; network work runs on
a worker thread and is delivered to the Tk thread through ``after`` polling.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from . import artifacts as ar
from .actions import WorkflowInfo, WorkflowRun


class _Worker:
    def __init__(self, win: tk.Toplevel, get_token: Callable[[], str]) -> None:
        self.win = win
        self.get_token = get_token
        self.busy = False
        self.closed = False

    def run(self, work: Callable[[str], Any], done: Callable[[Any], None], fail: Callable[[BaseException], None]) -> None:
        if self.busy or self.closed:
            return
        self.busy = True
        results: queue.Queue = queue.Queue(maxsize=1)

        def runner() -> None:
            try:
                results.put((work(self.get_token()), None))
            except BaseException as exc:  # noqa: BLE001 - reported on the Tk thread
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
            (done(result) if error is None else fail(error))

        threading.Thread(target=runner, name="AIWorkbenchBuildCenterDialog", daemon=True).start()
        self.win.after(50, check)


class DispatchDialog:
    """Form generated from the workflow's real ``workflow_dispatch.inputs``."""

    def __init__(
        self, parent: tk.Misc, *, svc: ar.GitHubDispatchService, owner: str, repo: str, workflow: WorkflowInfo,
        ref: str, get_token: Callable[[], str], known_run_ids: Callable[[], set[int]],
        on_result: Callable[[ar.DispatchResult], None], redact: Callable[[object], str] = str,
    ) -> None:
        self.svc, self.owner, self.repo, self.workflow = svc, owner, repo, workflow
        self.known_run_ids, self.on_result, self.redact = known_run_ids, on_result, redact
        self.form: ar.DispatchForm | None = None
        self.vars: dict[str, tk.Variable] = {}
        self.result: ar.DispatchResult | None = None
        self.win = tk.Toplevel(parent)
        self.win.title(f"Run workflow — {workflow.name}")
        self.win.transient(parent)
        self.worker = _Worker(self.win, get_token)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(self.win, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{owner}/{repo} · {workflow.path}", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Branch / tag (ref):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.ref_var = tk.StringVar(value=ref)
        ttk.Entry(frame, textvariable=self.ref_var, width=40).grid(row=1, column=1, sticky="we", pady=(8, 0))
        self.inputs_frame = ttk.LabelFrame(frame, text="Inputs (from the workflow file)", padding=6)
        self.inputs_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=8)
        self.status_var = tk.StringVar(value="Reading workflow inputs…")
        ttk.Label(frame, textvariable=self.status_var, wraplength=520, justify="left").grid(row=3, column=0, columnspan=2, sticky="w")
        bar = ttk.Frame(frame)
        bar.grid(row=4, column=0, columnspan=2, sticky="e", pady=(8, 0))
        self.btn_run = ttk.Button(bar, text="Run workflow", command=self.submit, state="disabled")
        self.btn_run.pack(side="right")
        ttk.Button(bar, text="Close", command=self.close).pack(side="right", padx=(0, 6))
        frame.columnconfigure(1, weight=1)
        self.worker.run(lambda t: self.svc.dispatch_form(t, owner, repo, workflow, ref=ref), self._form_loaded, self._fail)

    def close(self) -> None:
        self.worker.closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _fail(self, error: BaseException) -> None:
        self.status_var.set(f"[{getattr(error, 'category', type(error).__name__)}] {self.redact(error)}")
        self.btn_run.configure(state="normal" if self.form and self.form.dispatchable else "disabled")

    def _form_loaded(self, form: ar.DispatchForm) -> None:
        self.form = form
        if not form.dispatchable:
            self.status_var.set(form.error or "This workflow does not declare workflow_dispatch; it cannot be run manually.")
            return
        for row, spec in enumerate(form.inputs):
            label = spec.name + (" *" if spec.required else "")
            ttk.Label(self.inputs_frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            if spec.type == "boolean":
                var: tk.Variable = tk.BooleanVar(value=spec.default == "true")
                ttk.Checkbutton(self.inputs_frame, variable=var).grid(row=row, column=1, sticky="w")
            elif spec.type == "choice":
                var = tk.StringVar(value=spec.default if spec.default in spec.options else (spec.options[0] if spec.required else ""))
                ttk.Combobox(self.inputs_frame, textvariable=var, values=spec.options, state="readonly", width=30).grid(row=row, column=1, sticky="w")
            else:
                var = tk.StringVar(value=spec.default or "")
                ttk.Entry(self.inputs_frame, textvariable=var, width=40).grid(row=row, column=1, sticky="we")
            if spec.description:
                ttk.Label(self.inputs_frame, text=spec.description, foreground="#667085").grid(row=row, column=2, sticky="w", padx=(8, 0))
            self.vars[spec.name] = var
        if not form.inputs:
            ttk.Label(self.inputs_frame, text="This workflow takes no inputs.").grid(row=0, column=0, sticky="w")
        self.status_var.set("Ready. GitHub needs Actions: write on the token to start a run.")
        self.btn_run.configure(state="normal")

    def values(self) -> dict[str, object]:
        return {name: var.get() for name, var in self.vars.items()}

    def submit(self) -> None:
        if self.form is None or self.worker.busy:
            return
        try:
            ref = ar.validate_ref(self.ref_var.get())
            payload = ar.validate_dispatch_values(self.form.inputs, self.values())
        except ValueError as exc:
            self.status_var.set(str(exc))
            return
        known = set(self.known_run_ids())
        self.btn_run.configure(state="disabled")
        self.status_var.set(f"Requesting a run on '{ref}'…")
        form = self.form

        def work(token: str) -> ar.DispatchResult:
            res = self.svc.dispatch(token, self.owner, self.repo, self.workflow, ref=ref, inputs=payload, form=form)
            if res.state != "confirmed":
                import time as _t
                for _ in range(4):  # brief strict lookup; never guesses
                    _t.sleep(2.5)
                    res = self.svc.find_dispatched_run(token, self.owner, self.repo, res, known_run_ids=known)
                    if res.state == "confirmed" or "cannot tell" in res.message:
                        break
            return res

        def done(res: ar.DispatchResult) -> None:
            self.result = res
            if res.state == "confirmed":
                self.status_var.set(f"Run {res.run_id} started on '{res.ref}'. {res.message}")
            else:
                self.status_var.set(f"Not confirmed: {res.message} The request may still start a run; check the run list. Do not press Run again unless needed.")
            self.btn_run.configure(state="normal")
            self.on_result(res)

        self.worker.run(work, done, self._fail)


class ArtifactsDialog:
    """Artifacts of one run: list, download (with SHA-256) and safe extraction."""

    def __init__(
        self, parent: tk.Misc, *, svc: ar.GitHubDispatchService, owner: str, repo: str, run: WorkflowRun,
        get_token: Callable[[], str], redact: Callable[[object], str] = str,
        ask_directory: Callable[[], str] | None = None, confirm: Callable[[str, str], bool] | None = None,
        on_downloaded: Callable[[ar.ArtifactInfo, ar.DownloadResult], None] | None = None,
    ) -> None:
        self.svc, self.owner, self.repo, self.run = svc, owner, repo, run
        self.redact = redact
        self.ask_directory = ask_directory or (lambda: filedialog.askdirectory(parent=self.win, title="Save artifact to…"))
        self.confirm = confirm or (lambda title, msg: messagebox.askyesno(title, msg, parent=self.win))
        self.on_downloaded = on_downloaded
        self.artifacts: tuple[ar.ArtifactInfo, ...] = ()
        self.downloads: dict[int, ar.DownloadResult] = {}
        self._cancel = threading.Event()
        self.win = tk.Toplevel(parent)
        self.win.title(f"Artifacts — run {run.run_id}")
        self.win.geometry("980x420")
        self.win.transient(parent)
        self.worker = _Worker(self.win, get_token)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        top = ttk.Frame(self.win, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text=f"Run {run.run_id} · {run.head_branch} @ {run.head_sha[:7]} · {run.outcome}", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="Loading artifacts…")
        ttk.Label(top, textvariable=self.status_var, wraplength=940, justify="left").pack(anchor="w")
        self.tree = ttk.Treeview(self.win, columns=("size", "expires", "digest", "belongs", "local"), height=10)
        for col, text, width in (("#0", "Artifact", 220), ("size", "Size", 90), ("expires", "Expires (UTC)", 140),
                                 ("digest", "Reference digest", 150), ("belongs", "Run/commit", 110), ("local", "Downloaded", 220)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, stretch=col in {"#0", "local"})
        self.tree.pack(fill="both", expand=True, padx=8)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())
        bar = ttk.Frame(self.win, padding=8)
        bar.pack(fill="x")
        self.btn_download = ttk.Button(bar, text="Download…", command=self.download)
        self.btn_download.pack(side="left")
        self.btn_extract = ttk.Button(bar, text="Extract safely…", command=self.extract)
        self.btn_extract.pack(side="left", padx=(6, 0))
        self.btn_cancel = ttk.Button(bar, text="Cancel download", command=self._cancel.set)
        self.btn_cancel.pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Close", command=self.close).pack(side="right")
        self._update_buttons()
        self.worker.run(lambda t: self.svc.list_artifacts(t, owner, repo, run.run_id), self._loaded, self._fail)

    def close(self) -> None:
        self._cancel.set()
        self.worker.closed = True
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _fail(self, error: BaseException) -> None:
        self.status_var.set(f"[{getattr(error, 'category', type(error).__name__)}] {self.redact(error)}")
        self._update_buttons()

    def _loaded(self, items: tuple[ar.ArtifactInfo, ...]) -> None:
        self.artifacts = items
        self._render()
        self.status_var.set(f"{len(items)} artifact(s). Expired artifacts cannot be downloaded." if items else "This run has no artifacts.")

    def _render(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for a in self.artifacts:
            belongs = "yes" if ar.artifact_matches(a, run_id=self.run.run_id, head_sha=self.run.head_sha) else "NO"
            dl = self.downloads.get(a.artifact_id)
            local = ""
            if dl:
                local = {"matched": "✔ SHA-256 matches GitHub digest", "computed_only": "SHA-256 computed (no reference)"}.get(dl.verification, dl.verification)
            self.tree.insert("", "end", iid=str(a.artifact_id), text=a.name, values=(
                f"{a.size_in_bytes:,}", "EXPIRED" if a.expired else a.expires_at.replace("T", " ").replace("Z", "")[:16],
                (a.sha256_reference or "")[:12] + ("…" if a.sha256_reference else "none"), belongs, local))
        self._update_buttons()

    def selected(self) -> ar.ArtifactInfo | None:
        sel = self.tree.selection()
        return next((a for a in self.artifacts if str(a.artifact_id) == sel[0]), None) if sel else None

    def _update_buttons(self) -> None:
        a = self.selected()
        busy = self.worker.busy
        ok = bool(a and a.downloadable and ar.artifact_matches(a, run_id=self.run.run_id, head_sha=self.run.head_sha))
        self.btn_download.configure(state="normal" if ok and not busy else "disabled")
        self.btn_extract.configure(state="normal" if a and a.artifact_id in self.downloads and not busy else "disabled")
        self.btn_cancel.configure(state="normal" if busy else "disabled")

    def download(self) -> None:
        a = self.selected()
        if a is None or self.worker.busy:
            return
        folder = self.ask_directory()
        if not folder:
            return
        self._cancel.clear()
        self.status_var.set(f"Downloading {a.name}…")

        def done(res: ar.DownloadResult) -> None:
            self.downloads[a.artifact_id] = res
            note = "matches the digest GitHub reported" if res.verified else "computed; GitHub reported no digest to compare with (not verified)"
            self.status_var.set(f"Saved {res.path.name} ({res.size:,} bytes). SHA-256 {res.sha256} — {note}.")
            self._render()
            if self.on_downloaded:
                self.on_downloaded(a, res)

        self.worker.run(lambda t: self.svc.download_artifact(t, self.owner, self.repo, a, Path(folder), run=self.run, cancel=self._cancel.is_set), done, self._fail)
        self._update_buttons()

    def extract(self) -> None:
        a = self.selected()
        res = self.downloads.get(a.artifact_id) if a else None
        if res is None:
            return
        target = res.path.with_suffix("")
        try:
            files = ar.inspect_zip(res.path)
        except ar.UnsafeArchiveError as exc:
            self.status_var.set(f"Refused to extract: {exc}")
            return
        if not self.confirm("Extract artifact", f"Extract {len(files)} file(s) into a new folder?\n\n{target}"):
            return
        try:
            out = ar.safe_extract_zip(res.path, target)
        except (ar.UnsafeArchiveError, OSError) as exc:
            self.status_var.set(f"Refused to extract: {self.redact(exc)}")
            return
        self.status_var.set(f"Extracted {len(out)} file(s) into {target}.")
