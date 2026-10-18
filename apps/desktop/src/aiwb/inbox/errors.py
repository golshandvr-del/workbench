"""Stable import error codes and user-facing explanations (roadmap 1.16.1).

Codes never change once released. Display text is looked up by code and may be
reworded; tests and records only use the code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# code -> (stage, title, next step)
ERROR_CODES: dict[str, tuple[str, str, str]] = {
    "empty_response": ("capture", "The response is empty.",
                       "Copy the model's whole answer again and paste it."),
    "too_large": ("capture", "The response is larger than the 12 MB limit.",
                  "Ask the model to split the work into smaller responses."),
    "duplicate_response": ("capture", "This exact response was already captured.",
                           "Open the existing Inbox entry instead; nothing was stored twice."),
    "unknown_format": ("classify", "No supported response format was recognised.",
                       "Ask the model to answer with the protocol described in the prompt."),
    "json_invalid": ("parse", "The JSON in the response could not be read.",
                     "Use 'Repair prompt' so the model resends valid JSON."),
    "truncated": ("parse", "The response looks cut off (an unfinished block or JSON).",
                  "Use 'Repair prompt' to ask only for the missing or broken files."),
    "duplicate_path": ("parse", "The same file appears more than once in the response.",
                       "Ask the model to send each file exactly once."),
    "context_plan": ("parse", "This is a context plan, not an implementation response.",
                     "Use 'Import context plan' to select the requested files."),
    "protocol_invalid": ("validate", "The response does not follow the expected protocol.",
                         "Use 'Repair prompt'; the exact validation error is included."),
    "unsafe_path": ("validate", "A file path is unsafe (absolute, '..', reserved or outside the project).",
                    "Nothing was written. Ask the model to use project-relative paths only."),
    "attempt_unknown": ("reconcile", "The response names an attempt ID this project does not know.",
                        "Check that the answer belongs to this project; you can still review it."),
    "attempt_mismatch": ("reconcile", "The response belongs to a different task or attempt.",
                         "Do not apply it to the current task; re-send the current prompt."),
    "stale_base": ("reconcile", "Project files changed since the prompt for this answer was made.",
                   "Review the diff carefully or rebuild the prompt for the current files."),
    "partial_parse": ("salvage", "Only part of the response could be recovered.",
                      "Review the recovered files; use 'Repair prompt' for the rest."),
    "internal_error": ("parse", "An unexpected error occurred while reading the response.",
                       "The raw response is kept in the Inbox; export a diagnostics bundle."),
}

STAGES = ("capture", "classify", "parse", "validate", "reconcile", "salvage")


@dataclass
class ImportIssue:
    code: str
    stage: str
    details: str = ""
    kept: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in ERROR_CODES:
            raise ValueError(f"unknown import error code: {self.code}")

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "stage": self.stage, "details": self.details, "kept": self.kept, "extra": self.extra}

    @property
    def blocking(self) -> bool:
        return self.code not in ("attempt_unknown", "stale_base", "partial_parse", "duplicate_response")


def classify_error_message(message: str) -> str:
    """Map a Workbench validator message to a stable code (best effort, conservative)."""
    m = (message or "").lower()
    if "empty" in m and "response" in m:
        return "empty_response"
    if "too large" in m or "maximum response size" in m:
        return "too_large"
    if "context plan" in m:
        return "context_plan"
    if any(k in m for k in ("truncat", "unterminated", "incomplete", "missing <<<aiwb_end", "not closed", "unclosed")):
        return "truncated"
    if "duplicate" in m and ("path" in m or "file" in m or "destination" in m):
        return "duplicate_path"
    if any(k in m for k in ("absolute", "..", "outside", "reserved", "unsafe", "relative path", "path must", "drive")):
        return "unsafe_path"
    if "json" in m and any(k in m for k in ("invalid", "could not", "expecting", "decode", "parse")):
        return "json_invalid"
    if any(k in m for k in ("protocol", "unknown keys", "must be", "required", "expected")):
        return "protocol_invalid"
    return "unknown_format" if "format" in m or "no supported" in m else "protocol_invalid"


def explain(issue: ImportIssue | dict[str, Any]) -> str:
    """Plain-language explanation: what happened, where, what is safe, what to do next."""
    d = issue.to_dict() if isinstance(issue, ImportIssue) else issue
    stage, title, nxt = ERROR_CODES.get(d.get("code", ""), ERROR_CODES["internal_error"])
    lines = [f"[{d.get('code')}] {title}", f"Stage: {d.get('stage') or stage}",
             "Safe: the raw response is stored in the Inbox; no project file was changed."]
    if d.get("kept"):
        lines.append("Kept: " + str(d["kept"]))
    lines.append("Next: " + nxt)
    if d.get("details"):
        lines.append("Details: " + str(d["details"])[:600])
    return "\n".join(lines)
