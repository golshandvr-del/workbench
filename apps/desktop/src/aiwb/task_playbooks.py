"""Deterministic, review-first task playbooks used to shape model prompts."""
from __future__ import annotations
from typing import Any

PLAYBOOKS: dict[str, dict[str, Any]] = {
    "default": {
        "title": "General task",
        "description": "General-purpose quality workflow.",
        "phases": ["Confirm scope and acceptance criteria", "Inspect relevant existing context", "Implement the smallest complete change", "Run targeted tests and report evidence"],
        "acceptance": ["Preserve unrelated behavior", "Document assumptions and unverified checks"],
    },
    "feature": {
        "title": "Feature implementation",
        "description": "Add a user-visible capability while preserving existing behavior.",
        "phases": ["Define user story, boundaries, and acceptance criteria", "Trace the current architecture and affected interfaces", "Implement domain logic separately from UI where practical", "Add positive, negative, edge-case, and regression tests", "Update help and release notes"],
        "acceptance": ["No feature is considered complete without tests or a justified test gap", "Existing data and saved settings remain compatible"],
    },
    "bugfix": {
        "title": "Bug investigation and repair",
        "description": "Identify a reproducible root cause and prove the fix.",
        "phases": ["Reproduce the reported failure and capture the exact symptom", "Trace the faulty path to a root cause rather than masking the symptom", "Add a regression test that fails before the fix", "Make a narrowly scoped correction", "Run the regression test and nearby tests"],
        "acceptance": ["Do not claim a fix without reproduction or equivalent evidence", "Do not weaken validation merely to make the test pass"],
    },
    "refactor": {
        "title": "Architecture refactor",
        "description": "Improve boundaries and maintainability without changing behavior unintentionally.",
        "phases": ["Map current responsibilities, imports, state ownership, and side effects", "Write down compatibility contracts and public entry points", "Extract one cohesive domain/service boundary at a time", "Keep dependency direction inward and avoid circular imports", "Run equivalence and regression tests after each extraction"],
        "acceptance": ["Behavioral changes must be explicit, not accidental", "A module split must reduce coupling, not just move lines"],
    },
    "security": {
        "title": "Security review and hardening",
        "description": "Review untrusted inputs, privilege boundaries, persistence, and recovery paths.",
        "phases": ["Define assets, trust boundaries, and attacker-controlled inputs", "Trace path handling, deserialization, subprocesses, secrets, and permissions", "Create negative tests for traversal, symlinks, stale state, and malformed input", "Implement defense in depth with fail-closed behavior", "Document residual risks and operational controls"],
        "acceptance": ["Do not label a pattern check as a sandbox", "Preserve auditable evidence and safe recovery behavior"],
    },
    "performance": {
        "title": "Performance investigation",
        "description": "Measure first and preserve correctness under load.",
        "phases": ["Define a representative workload and performance objective", "Measure baseline and identify the dominant cost", "Change the smallest hot path and preserve semantics", "Benchmark again and test bounded memory / cancellation", "Report environment, method, before/after results, and uncertainty"],
        "acceptance": ["Avoid optimization claims without measurements", "Keep GUI work non-blocking for long-running operations"],
    },
    "documentation": {
        "title": "Documentation and release readiness",
        "description": "Make documentation accurate, navigable, and consistent with the delivered source.",
        "phases": ["Inventory entry points, supported platforms, dependencies, and constraints", "Check all examples and commands against actual files", "Reconcile README, architecture, changelog, and release checklist", "Mark untested platform behavior honestly", "Add a file map and reproducible verification instructions"],
        "acceptance": ["Documentation must not overstate test coverage or platform verification", "Use one canonical version number across release artifacts"],
    },
    "engineering_simulation": {
        "title": "Engineering / simulation workflow",
        "description": "Keep model assumptions, simulator evidence, and results distinguishable.",
        "phases": ["List inputs, units, assumptions, governing equations, and acceptance thresholds", "Inspect native project files and dependencies before editing", "Make traceable, minimal model changes", "Validate structural consistency and run the intended simulator when available", "Separate calculated estimates from simulator-observed results and list reproducible steps"],
        "acceptance": ["Never claim simulator execution without observed logs or result files", "Preserve units, coordinate systems, connectivity, and model provenance"],
    },
}


def render_playbook(playbook_id: str) -> str:
    """Render one known playbook as concise prompt instructions; unknown IDs fail closed."""
    item = PLAYBOOKS.get(str(playbook_id or "default"))
    if item is None:
        raise ValueError(f"Unknown task playbook: {playbook_id}")
    lines = [f"## Task playbook: {item['title']}", str(item["description"]), "Execution sequence:"]
    lines.extend(f"{i}. {step}" for i, step in enumerate(item["phases"], 1))
    lines.append("Acceptance rules:")
    lines.extend(f"- {rule}" for rule in item["acceptance"])
    lines.append("Use only the stages relevant to this task; do not add unnecessary scaffolding.")
    return "\n".join(lines)


def playbook_catalog() -> list[tuple[str, str]]:
    return [(key, value["title"]) for key, value in PLAYBOOKS.items()]
