"""Import pipeline: Capture → Classify → Parse → Validate → Reconcile (roadmap 1.16.0/1.16.1).

Each stage reports its own result and issues. A failure never deletes the raw
response, never writes project files (import only produces a validated payload
for the existing preview/diff/apply flow) and can be re-run later (*reparse*).
The host app injects its strict validator so this package stays UI- and
protocol-independent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .attempts import Attempt, AttemptRegistry, declared_attempt_id
from .classify import Suggestion, classify, looks_truncated
from .errors import ImportIssue, classify_error_message
from .salvage import SalvageResult, salvage_aiwb_blocks
from .store import InboxStore, RawResponse

# validate(text) -> (payload, changes, format_name); raises on any problem.
Validator = Callable[[str], tuple[dict[str, Any], list[Any], str]]

PIPELINE_VERSION = 1


@dataclass
class CaptureOutcome:
    response: RawResponse | None
    duplicate: bool = False
    issue: ImportIssue | None = None


@dataclass
class PipelineOutcome:
    response: RawResponse
    status: str = "failed"                      # parsed | partial | failed
    stages: dict[str, str] = field(default_factory=dict)  # stage -> ok | failed | warn | skipped
    suggestions: list[Suggestion] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    payload: dict[str, Any] | None = None
    changes: list[Any] = field(default_factory=list)
    format_name: str = ""
    attempt: Attempt | None = None
    salvage: SalvageResult | None = None

    @property
    def salvage_paths(self) -> list[str]:
        return sorted(self.salvage.complete) if self.salvage else []

    @property
    def can_preview(self) -> bool:
        return self.payload is not None and not any(i.blocking for i in self.issues)


class ImportPipeline:
    def __init__(self, store: InboxStore, attempts: AttemptRegistry, validate: Validator, *,
                 current_task_id: Callable[[], str] = lambda: "",
                 current_base_revision: Callable[[], str] = lambda: "",
                 redact: Callable[[str], str] = lambda s: s,
                 path_problem: Callable[[str], str] | None = None,
                 parse_block: Callable[[str], dict[str, Any]] | None = None,
                 validate_payload: Callable[[dict[str, Any]], tuple[dict[str, Any], list[Any]]] | None = None) -> None:
        self.store, self.attempts, self.validate = store, attempts, validate
        self.current_task_id, self.current_base_revision = current_task_id, current_base_revision
        self.redact = redact
        self.path_problem = path_problem
        self.parse_block = parse_block
        self.validate_payload = validate_payload

    # -- stage 1: capture (raw first, always)
    def capture_text(self, text: str | bytes, *, source: str = "paste", attempt_id: str = "") -> CaptureOutcome:
        s = text.decode("utf-8", errors="replace") if isinstance(text, bytes) else (text or "")
        if not s.strip():
            return CaptureOutcome(None, issue=ImportIssue("empty_response", "capture"))
        declared = declared_attempt_id(s)
        try:
            rec, dup = self.store.capture(text, source=source, attempt_id=attempt_id or declared,
                                          declared_attempt_id=declared, task_id=self.current_task_id())
        except ValueError:
            return CaptureOutcome(None, issue=ImportIssue("too_large", "capture"))
        return CaptureOutcome(rec, dup, ImportIssue("duplicate_response", "capture", rec.response_id) if dup else None)

    # -- stages 2–5
    def process(self, response_id: str) -> PipelineOutcome:
        rec = self.store.get(response_id)
        if rec is None:
            raise KeyError(response_id)
        text = self.store.read_text(response_id)
        out = PipelineOutcome(rec)
        out.stages["capture"] = "ok"

        out.suggestions = classify(text)
        out.stages["classify"] = "ok" if out.suggestions else "warn"
        if not out.suggestions:
            out.issues.append(ImportIssue("unknown_format", "classify"))

        if out.suggestions and out.suggestions[0].parser == "context_request":
            out.format_name = "AIWB_CONTEXT_REQUEST"
            out.stages["parse"] = "ok"
            out.issues.append(ImportIssue("context_request", "parse"))
            self._reconcile(text, out)
            out.status = "context_request"
            self.store.add_parse_result(response_id, {
                "pipeline_version": PIPELINE_VERSION, "status": out.status, "stages": out.stages,
                "format": out.format_name, "suggestions": [s.parser for s in out.suggestions],
                "issues": [i.to_dict() for i in out.issues], "file_paths": [], "salvaged": []})
            out.response = self.store.get(response_id) or out.response
            return out
        try:
            out.payload, out.changes, out.format_name = self.validate(text)
            out.stages["parse"] = out.stages["validate"] = "ok"
        except Exception as exc:  # noqa: BLE001 - every failure becomes a coded issue
            msg = self.redact(str(exc))
            code = classify_error_message(msg)
            if code in ("protocol_invalid", "json_invalid", "unknown_format") and looks_truncated(text):
                code = "truncated"
            if out.suggestions or code != "protocol_invalid":
                out.issues = [i for i in out.issues if i.code != "unknown_format"] if code != "unknown_format" else out.issues
            stage = "validate" if code in ("protocol_invalid", "unsafe_path") else "parse"
            out.stages[stage] = "failed"
            if code not in {i.code for i in out.issues}:
                out.issues.append(ImportIssue(code, stage, msg[:600]))
            if any(s.parser == "aiwb_blocks" for s in out.suggestions):
                self._salvage(text, out)

        self._reconcile(text, out)

        blocking = any(i.blocking for i in out.issues)
        if out.payload is not None and not blocking:
            out.status = "parsed"
        elif out.salvage and out.salvage.any_recovered:
            out.status = "partial"
        else:
            out.status = "failed"
        self.store.add_parse_result(response_id, {
            "pipeline_version": PIPELINE_VERSION, "status": out.status, "stages": out.stages,
            "format": out.format_name, "suggestions": [s.parser for s in out.suggestions],
            "issues": [i.to_dict() for i in out.issues], "file_paths": sorted(self._paths(out)),
            "salvaged": out.salvage_paths,
        })
        if out.attempt and out.status == "parsed" and not any(i.code == "attempt_mismatch" for i in out.issues):
            self.attempts.mark(out.attempt.attempt_id, "answered")
        out.response = self.store.get(response_id) or out.response
        return out

    def reparse(self, response_id: str) -> PipelineOutcome:
        """Run the pipeline again on the stored raw bytes (no new capture, no model call)."""
        return self.process(response_id)

    # -- helpers
    @staticmethod
    def _paths(out: PipelineOutcome) -> list[str]:
        paths = []
        for f in (out.payload or {}).get("files", []) if isinstance(out.payload, dict) else []:
            if isinstance(f, dict) and isinstance(f.get("path"), str):
                paths.append(f["path"])
        return paths

    def _salvage(self, text: str, out: PipelineOutcome) -> None:
        expected: list[str] = []
        att = self.attempts.get(out.response.attempt_id) if out.response.attempt_id else None
        if att:
            expected = list(att.expected_paths)
        kw: dict[str, Any] = {"redact": self.redact}
        if self.path_problem:
            kw["path_problem"] = self.path_problem
        if self.parse_block:
            kw["parse_block"] = self.parse_block
        res = salvage_aiwb_blocks(text, expected, **kw)
        out.salvage = res
        out.stages["salvage"] = "ok" if res.any_recovered else "failed"
        if not res.any_recovered:
            return
        kept = ", ".join(sorted(res.complete))[:400]
        out.issues.append(ImportIssue(
            "partial_parse", "salvage", self.redact(", ".join(sorted(res.broken)))[:400], kept=kept,
            extra={"broken": {self.redact(k): self.redact(v) for k, v in res.broken.items()},
                   "duplicates": res.duplicates, "missing": res.missing}))
        if self.validate_payload:
            try:
                payload = {"protocol": "workbench-v2", "summary": "Recovered part of a partial response",
                           "files": res.payload_files}
                out.payload, out.changes = self.validate_payload(payload)
                out.format_name = "Recovered AIWB blocks (partial)"
            except Exception as exc:  # noqa: BLE001
                out.payload, out.changes = None, []
                out.salvage.broken.update({p: "failed validation: " + self.redact(str(exc))[:200] for p in res.complete})
                out.salvage.complete.clear()

    def _reconcile(self, text: str, out: PipelineOutcome) -> None:
        rec = out.response
        aid = rec.declared_attempt_id or rec.attempt_id
        current_task = self.current_task_id()
        if not aid:
            out.stages["reconcile"] = "skipped"
            return
        att = self.attempts.get(aid)
        out.attempt = att
        if att is None:
            out.issues.append(ImportIssue("attempt_unknown", "reconcile", aid))
            out.stages["reconcile"] = "warn"
            return
        if rec.attempt_id and rec.declared_attempt_id and rec.attempt_id != rec.declared_attempt_id:
            out.issues.append(ImportIssue("attempt_mismatch", "reconcile",
                                          f"linked {rec.attempt_id}, text says {rec.declared_attempt_id}"))
        elif current_task and att.task_id and att.task_id != current_task:
            out.issues.append(ImportIssue("attempt_mismatch", "reconcile",
                                          f"answer is for task {att.task_id}; current task is {current_task}"))
        base = self.current_base_revision()
        if base and att.base_revision and base != att.base_revision:
            out.issues.append(ImportIssue("stale_base", "reconcile",
                                          f"prompt base {att.base_revision[:12]}, project now {base[:12]}"))
        out.stages["reconcile"] = "failed" if any(i.code == "attempt_mismatch" for i in out.issues) else (
            "warn" if any(i.code == "stale_base" for i in out.issues) else "ok")
