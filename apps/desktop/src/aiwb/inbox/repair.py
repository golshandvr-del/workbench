"""Smart repair prompts from real Inbox evidence (roadmap 1.16.2).

The repair section is built only from what Workbench observed: the attempt and
task the answer belongs to, the stable error codes, which files were received
intact (must not be regenerated), which are broken/missing, and the exact
response format. Every repair is a new attempt linked to its parent; a chain of
more than ``MAX_REPAIR_CHAIN`` consecutive repairs needs a human decision
instead of yet another automatic repair prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .attempts import Attempt, AttemptRegistry, prompt_identity_block
from .errors import ERROR_CODES
from .pipeline import PipelineOutcome

MAX_REPAIR_CHAIN = 3


@dataclass
class RepairPlan:
    attempt: Attempt | None
    chain_depth: int
    needs_decision: bool
    section: str
    keep: list[str] = field(default_factory=list)
    redo: list[str] = field(default_factory=list)


def repair_chain_depth(registry: AttemptRegistry, attempt_id: str) -> int:
    """Number of consecutive *repair* attempts ending at ``attempt_id`` (cycle-safe)."""
    depth, seen, cur = 0, set(), registry.get(attempt_id) if attempt_id else None
    while cur is not None and cur.attempt_id not in seen and cur.kind == "repair":
        seen.add(cur.attempt_id)
        depth += 1
        cur = registry.get(cur.parent_attempt_id) if cur.parent_attempt_id else None
    return depth


def plan_repair(outcome: PipelineOutcome, registry: AttemptRegistry, *, base_revision: str = "",
                task_id: str = "", max_chain: int = MAX_REPAIR_CHAIN, register: bool = True) -> RepairPlan:
    parent_id = outcome.response.declared_attempt_id or outcome.response.attempt_id
    parent = registry.get(parent_id) if parent_id else None
    depth = repair_chain_depth(registry, parent_id) if parent else 0
    keep = sorted(outcome.salvage.complete) if outcome.salvage else []
    redo: list[str] = []
    if outcome.salvage:
        redo = sorted(set(outcome.salvage.broken) | set(outcome.salvage.duplicates) | set(outcome.salvage.missing))
    needs_decision = depth >= max_chain
    attempt = None
    if register and not needs_decision:
        attempt = registry.new(task_id=(parent.task_id if parent else task_id),
                               task_revision=(parent.task_revision if parent else ""),
                               base_revision=base_revision or (parent.base_revision if parent else ""),
                               kind="repair", parent_attempt_id=parent_id if parent else "",
                               expected_paths=redo or (list(parent.expected_paths) if parent else []))
    lines: list[str] = []
    if attempt:
        lines += [prompt_identity_block(attempt), ""]
    lines.append("## Evidence from AI Workbench's Response Inbox (observed, authoritative)")
    lines.append(f"- Response: {outcome.response.response_id} (SHA-256 {outcome.response.sha256[:16]}…), status {outcome.status}")
    if parent:
        lines.append(f"- Answers attempt {parent.attempt_id} for task {parent.task_id or '(unknown)'}; "
                     f"repair round {depth + 1} of at most {max_chain}")
    elif parent_id:
        lines.append(f"- The answer named attempt {parent_id}, which this project does not know")
    for issue in outcome.issues:
        title = ERROR_CODES.get(issue.code, ("", issue.code, ""))[1]
        detail = f" — {issue.details}" if issue.details else ""
        lines.append(f"- [{issue.code}] stage {issue.stage}: {title}{detail[:400]}")
    if keep:
        lines += ["", "Received intact — do NOT regenerate or change these files:"] + [f"- {p}" for p in keep]
    if redo:
        lines += ["", "Send again, each complete (only these):"]
        for p in redo:
            why = (outcome.salvage.broken.get(p) if outcome.salvage else "") or (
                "sent more than once" if outcome.salvage and p in outcome.salvage.duplicates else "missing")
            lines.append(f"- {p} ({why})")
    if needs_decision:
        lines += ["", f"STOP: {depth} consecutive repair rounds already failed. Do not generate another repair "
                      "automatically; the user must decide (split the task, change the format, or rewrite the prompt)."]
    return RepairPlan(attempt, depth, needs_decision, "\n".join(lines), keep, redo)
