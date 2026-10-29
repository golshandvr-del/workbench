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
                                           ("new_quick", "Quick — one AI chat…"),  # 5.14.0: replaces the 1.x pages
                                           ("new_folder", "Add existing folder…"))),
    ("open", "Open", "open", ()),
    ("save", "Save", "save", ()),
    ("run", "Run", "run", ()),
)

# 5.14.0: Quick (New Project ▾) replaced the 1.x Prompt / AI Response pages; Settings keeps the two other 1.x pages
# (Project Profile, Run & Report) under a plain "Tools" section. The name CLASSIC is kept for callers.
CLASSIC = "Tools"

# Rail destinations: (key, label, icon, sections). 5.13.0 (owner audit B3/B4): four — one project, one screen.
# Projects left the rail: the open project is switched in the toolbar (PROJECT_MENU); its settings are Settings › Project.
RAIL: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("home", "Home", "home", ("Next step", "Mission Map", "Task details")),  # 5.11.0: the cockpit card
    ("agents", "Agents", "agents", ("Team", "Selected AI", "Balance", "Dispatch desk")),
    ("history", "History", "history", ("Timeline", "One list", "Selected step", "Tools")),
    ("settings", "Settings", "settings", ("Appearance", "Experience", "Motion", "Application", "Project",
                                          CLASSIC)),
)

# The phone keeps its own five destinations (roadmap 6.0.0; mobile is paused — 5.13.0 changes the desktop only).
MOBILE_BAR: tuple[tuple[str, str, str], ...] = (
    ("home", "Home", "home"),
    ("projects", "Projects", "projects"),
    ("agents", "Agents", "agents"),
    ("history", "History", "history"),
    ("settings", "Settings", "settings"),
)

# Toolbar › project switcher ("<name> ▾", 5.13.0): the recent projects, then these fixed items.
PROJECT_MENU: tuple[tuple[str, str], ...] = (
    ("all_projects", "All projects…"),
    ("reveal_project", "Reveal folder"),
)

# The expert pages of 3.x/4.x (page key, label), each reached from the "Tools" section of the destination it belongs to.
# 5.14.0: Prompt and AI Response left the app's navigation (Quick replaces them); Project Profile and Run & Report are
# Settings › Tools; Git stays with the past (History).
TOOLS: tuple[tuple[str, str], ...] = (
    ("profile", "Project Profile"),
    ("run", "Run & Report"),
    ("git", "Git / GitHub"),
)
TOOL_HOME: dict[str, str] = {"profile": "settings", "run": "settings", "git": "history"}


def tools_of(dest: str) -> tuple[tuple[str, str], ...]:
    """The expert pages listed under ``dest`` › Tools, in :data:`TOOLS` order."""
    return tuple(t for t in TOOLS if TOOL_HOME[t[0]] == dest)

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
        "Toolbar": {**{label: {c[1]: {} for c in kids} for _id, label, _i, kids in TOOLBAR},
                    "Project switcher": {"Recent projects": {}, **{label: {} for _id, label in PROJECT_MENU}}},
        "Rail": {label: ({s: ({t[1]: {} for t in tools_of(k)} if s in ("Tools", CLASSIC) else {}) for s in sections})
                 for k, label, _i, sections in RAIL},
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
