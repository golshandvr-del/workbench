"""Every command of the application by one id (roadmap 5.13.0, owner audit B5).

Before 5.13.0 the App Map audit compared *labels*: "Copy prompt", "Prepare prompt for this task" and "COPY PROMPT" were
three commands to it, so the same job could live in three places as long as the words differed. Here each job has one
id, the labels it goes by (synonyms) and the places where a label means that job — the audit
(:func:`aiwb.ui.ui_map.two_homes`) groups by id, so **one job = one home**.

A label that is not registered is its own command (``label:<normalised label>``): new buttons stay covered without an
entry here; an entry is needed only when two different words mean the same job, or one word means different jobs in
different places (History's "Copy prompt" copies a past prompt, the task menu's copies the task's next prompt).

``where`` is a tuple of App Map page paths (``"Home"``, ``"Settings › Project"``, ``"Toolbar"`` …); a label means the
command when the node's page path starts with one of them. ``()`` = anywhere. Outside those places a label that only
one command uses still means that command (its home is where it belongs; anywhere else is a second home).
"""
from __future__ import annotations

import re
from typing import NamedTuple


class Command(NamedTuple):
    id: str
    labels: tuple[str, ...]
    where: tuple[str, ...] = ()
    doc: str = ""


COMMANDS: tuple[Command, ...] = (
    # -- the task loop (Home: task menu on the Mission Map, Next-step card) — one home: Home
    Command("task.copy_prompt", ("COPY PROMPT", "Copy prompt", "Prepare prompt for this task", "Prepare the prompt",
                                 "Copy the prompt again", "Copy again"), ("Home", "Settings › Project"),
            "Prepare a task's prompt for its AI and copy it."),
    Command("task.sent", ("SEND PROMPT", "I sent it"), ("Home", "Settings › Project"),
            "Record that the prompt was pasted into the AI's chat."),
    Command("task.paste_answer", ("GET AI RESPONSE", "Check & import answer", "Paste the answer", "Import answer…"),
            ("Home", "Settings › Project"), "Paste the AI's answer, check it and take its files."),
    Command("task.done", ("MARK AS DONE", "Accept the delivery"), ("Home", "Settings › Project"),
            "Accept the task's delivery."),
    Command("task.open", ("Open task in Workbench", "Open task"), ("Home",), "Show a task's details."),
    # -- projects (Toolbar › project switcher) — one home: the toolbar
    Command("project.library", ("All projects…", "Projects…", "Open project list"), ("Toolbar",),
            "The project library: create, open, find, reveal, remove."),
    Command("project.reveal", ("Reveal folder", "Open project folder"), ("Toolbar",),
            "Open the project's folder in the file manager."),
    Command("project.new", ("New Project", "+ New project", "Guided project (recommended)"), ("Toolbar",),
            "Create a project with the wizard."),
    Command("project.settings", ("Project settings…",), ("Settings",), "The open project's settings page."),
    # -- Agents
    Command("agents.prepare_all", ("Prepare all prompts",), ("Agents",), "Prepare every ready task's prompt."),
    Command("agents.edit_team", ("Edit team…",), ("Agents",), "Add, rename or remove the project's AIs."),
    # -- History: the past (copying a past prompt is not the task loop's "Copy prompt")
    Command("history.copy_prompt", ("Copy prompt",), ("History",), "Copy the prompt of a past step."),
    Command("history.copy_output", ("Copy model output",), ("History",), "Copy the answer of a past step."),
    Command("history.versions", ("Project versions…",), ("History",), "The project's saved versions."),
    # -- Classic tools (1.x) — kept until Quick mode replaces them (5.14.0); their words mean their own jobs
    Command("classic.copy_prompt", ("Copy prompt",), ("Settings › Classic tools (1.x)",),
            "Copy the prompt built on the 1.x Prompt page."),
    # -- application
    Command("app.map", ("App Map…",), ("Settings",), "Every place and command of the application."),
    Command("app.restore", ("Restore Manager…",), (), "Undo applied changes."),
    Command("app.validation", ("Validation Profiles…",), (), "Build/test commands per project type."),
    Command("app.companion", ("Mobile Companion…",), (), "Pair the phone app."),
)


def norm(label: str) -> str:
    """Comparable form of a label: lower case, letters and digits, no ``+``/``…``/``▾``."""
    return re.sub(r"[^a-z0-9]+", " ", label.lower().replace("+", "")).strip()


def _in(path: str, where: tuple[str, ...]) -> bool:
    return not where or any(path == w or path.startswith(w + " › ") for w in where)


def command_of(path: str, label: str) -> str:
    """The command id of the control ``label`` found on the page ``path`` (``"label:<norm>"`` when unregistered)."""
    n = norm(label)
    named = [c for c in COMMANDS if any(norm(x) == n for x in c.labels)]
    for c in named:
        if _in(path, c.where):
            return c.id
    if len(named) == 1:  # a word of one job only is that job everywhere — so a second home of it is caught
        return named[0].id
    return "label:" + n


def label(command_id: str) -> str:
    """The first (preferred) label of a registered command."""
    for c in COMMANDS:
        if c.id == command_id:
            return c.labels[0]
    raise KeyError(command_id)


def ids() -> list[str]:
    return [c.id for c in COMMANDS]
