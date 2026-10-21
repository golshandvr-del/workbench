"""The 5.x interface structure as data (roadmap 5.0.0, docs/UI_TREE.md).

``docs/UI_TREE.md`` is the human tree; this module is the same tree for the code. ``test_ui_tree.py`` parses the
Markdown and requires it to equal these tables, so adding, renaming or moving a destination, toolbar command, tab or
menu item without updating the tree turns CI red.

Rules (owner request 2026-10-20): every node has at most :data:`MAX_CHILDREN` direct children (Miller), every
command has exactly one home, labels are unique among siblings.
"""
from __future__ import annotations

from typing import Any

MAX_CHILDREN = 7

# Toolbar: (id, label, icon, menu children)
TOOLBAR: tuple[tuple[str, str, str, tuple[tuple[str, str], ...]], ...] = (
    ("new", "New Project", "plus_circle", (("new_guided", "Guided project (recommended)"),
                                           ("new_folder", "Add existing folder…"))),
    ("open", "Open", "open", ()),
    ("save", "Save", "save", ()),
    ("run", "Run", "run", ()),
)

# Rail destinations: (key, label, icon, sections)
RAIL: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("home", "Home", "home", ("Mission Map", "Task details", "Your projects")),
    ("projects", "Projects", "projects", ("Project cards", "Project Workbench")),
    ("agents", "Agents", "agents", ("Team", "Dispatch desk", "Tools")),
    ("history", "History", "history", ("Timeline", "Prompts & responses", "Versions")),
    ("settings", "Settings", "settings", ("Appearance", "Experience", "Motion", "Application")),
)

# Tools reached from Agents › Tools: the expert pages of 3.x/4.x (page key, label).
TOOLS: tuple[tuple[str, str], ...] = (
    ("prompt", "Prompt"),
    ("response", "AI Response"),
    ("profile", "Project Profile"),
    ("run", "Run & Report"),
    ("git", "Git / GitHub"),
)

# Right-click menu of a task circle on the Mission Map: (id, label, icon, guide actions that enable it)
TASK_MENU: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("copy_prompt", "COPY PROMPT", "copy", ("copy", "prepare")),
    ("send_prompt", "SEND PROMPT", "send", ("sent",)),
    ("get_response", "GET AI RESPONSE", "sparkle", ("paste",)),
    ("mark_done", "MARK AS DONE", "check", ("accept_handoff", "approve", "validation_passed", "waive_validation")),
)

STATUS_BAR: tuple[str, ...] = ("Agents running", "Milestone", "Autosaved")


def tree() -> dict[str, Any]:
    """The whole tree as nested ``{label: children}`` (used by the tests and by ``UI_TREE.md``)."""
    return {
        "Toolbar": {label: {c[1]: {} for c in kids} for _id, label, _i, kids in TOOLBAR},
        "Rail": {label: ({s: ({t[1]: {} for t in TOOLS} if s == "Tools" else {}) for s in sections})
                 for _k, label, _i, sections in RAIL},
        "Task menu": {label: {} for _id, label, _i, _a in TASK_MENU},
        "Status bar": {s: {} for s in STATUS_BAR},
    }


def violations(node: dict[str, Any] | None = None, path: str = "") -> list[str]:
    """Rule breaks of the tree (too many children)."""
    node = tree() if node is None else node
    out = []
    if len(node) > MAX_CHILDREN:
        out.append(f"{path or '/'} has {len(node)} children (max {MAX_CHILDREN})")
    for k, v in node.items():
        out += violations(v, f"{path}/{k}")
    return out
