#!/usr/bin/env python3
"""Rebuild the 5.10.0 answer corpus (``corpus.json`` + one file per answer) in this folder.

The stored files are the corpus; this script only documents how each one was made and lets them be rebuilt.
Every answer imitates a shape a chat app really returns (see ``style``). They are **reconstructed** — the sandbox that
built them had no access to the chat apps — so ``source`` says so; answers the owner pastes that fail are added here
as ``source: owner`` cases (roadmap §5 rule 2).

Scenario: ``tests/answer_corpus.py`` (Todo CLI · Project manager, Core dev, CLI dev, QA · state revision 2).

    python build_corpus.py            # rewrites this folder
    python build_corpus.py OUT_DIR    # writes somewhere else
"""
from __future__ import annotations

import copy
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ATT = "att-20261022-120000-0a1b2c3d"   # = answer_corpus.ATTEMPT, replaced by the real attempt id on replay

CHARTER = {
    "schema_version": "1.0", "base_state_revision": 2,
    "project": {"name": "Todo CLI", "goal": "A command-line todo app in Python with JSON storage",
                "summary": "A small standard-library Python CLI. A core package keeps todos in a JSON file; a thin CLI "
                           "layer parses commands; QA writes the tests."},
    "architecture": {"summary": "Core package (model + JSON store) used by an argparse CLI; tests beside them.",
                     "modules": [
                         {"id": "core", "purpose": "Todo model and JSON storage", "paths": ["src/todo/**"],
                          "depends_on": [], "owner_agent_id": "agent-core-dev"},
                         {"id": "cli", "purpose": "argparse commands add/list/done/remove", "paths": ["src/cli/**"],
                          "depends_on": ["core"], "owner_agent_id": "agent-cli-dev"},
                         {"id": "tests", "purpose": "unittest suite", "paths": ["tests/**"],
                          "depends_on": ["core", "cli"], "owner_agent_id": "agent-qa"}]},
    "coordination": {"file_ownership": [{"agent_id": "agent-core-dev", "paths": ["src/todo/**"]},
                                        {"agent_id": "agent-cli-dev", "paths": ["src/cli/**"]},
                                        {"agent_id": "agent-qa", "paths": ["tests/**"]}],
                     "sync_points": [{"after_milestone": "m1",
                                      "description": "The core API in src/todo/__init__.py is frozen before the CLI "
                                                     "starts."}]},
    "roadmap": {"milestones": [
        {"ref": "m1", "title": "Core storage", "version": "0.1.0",
         "criteria": ["Todos can be added, listed, completed and removed through the core API",
                      "Data survives a restart"]},
        {"ref": "m2", "title": "Usable CLI", "version": "0.2.0",
         "criteria": ["todo add/list/done/remove work from a terminal", "All tests pass"]}]},
    "tasks": [
        {"ref": "t1", "title": "Core model and JSON store",
         "objective": "Todo dataclass, TodoStore with add/list/complete/remove, atomic JSON save",
         "owner_agent_id": "agent-core-dev", "milestone_ref": "m1", "depends_on_refs": [],
         "scope": {"include": ["src/todo/**"]},
         "acceptance_criteria": ["TodoStore round-trips through JSON", "No third-party packages"]},
        {"ref": "t2", "title": "Core tests", "objective": "unittest coverage of the core API",
         "owner_agent_id": "agent-qa", "milestone_ref": "m1", "depends_on_refs": ["t1"],
         "scope": {"include": ["tests/**"]}, "acceptance_criteria": ["python -m unittest passes"]},
        {"ref": "t3", "title": "CLI commands", "objective": "argparse entry point with add, list, done, remove",
         "owner_agent_id": "agent-cli-dev", "milestone_ref": "m2", "depends_on_refs": ["t1"],
         "scope": {"include": ["src/cli/**"]},
         "acceptance_criteria": ["python -m cli add 'x' then list shows it"]},
        {"ref": "t4", "title": "CLI tests", "objective": "Tests that run the CLI in a temp folder",
         "owner_agent_id": "agent-qa", "milestone_ref": "m2", "depends_on_refs": ["t3"],
         "scope": {"include": ["tests/**"]}, "acceptance_criteria": ["CLI tests pass on Windows"]}],
    "risks": ["Concurrent runs could overwrite the JSON file."],
    "questions_for_user": ["Should completed todos be kept or deleted?"],
}

FILES = {
    "src/todo/__init__.py": '"""Todo core API."""\nfrom .model import Todo\nfrom .store import TodoStore\n\n'
                            '__all__ = ["Todo", "TodoStore"]\n',
    "src/todo/model.py": "from __future__ import annotations\n\nfrom dataclasses import dataclass, field\nimport uuid\n\n\n"
                         "@dataclass\nclass Todo:\n    title: str\n    done: bool = False\n"
                         "    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])\n",
    "src/todo/store.py": (
        "from __future__ import annotations\n\nimport json\nimport os\nfrom dataclasses import asdict\n"
        "from pathlib import Path\n\nfrom .model import Todo\n\n\nclass TodoStore:\n"
        '    """Todos in one JSON file, saved atomically."""\n\n'
        "    def __init__(self, path: Path) -> None:\n        self.path = Path(path)\n"
        "        self.items: list[Todo] = []\n        if self.path.exists():\n"
        '            self.items = [Todo(**x) for x in json.loads(self.path.read_text(encoding="utf-8"))]\n\n'
        "    def add(self, title: str) -> Todo:\n        t = Todo(title)\n        self.items.append(t)\n"
        "        self.save()\n        return t\n\n"
        "    def complete(self, todo_id: str) -> None:\n"
        "        next(t for t in self.items if t.id == todo_id).done = True\n        self.save()\n\n"
        "    def remove(self, todo_id: str) -> None:\n"
        "        self.items = [t for t in self.items if t.id != todo_id]\n        self.save()\n\n"
        "    def save(self) -> None:\n        tmp = self.path.with_suffix(\".tmp\")\n"
        "        tmp.write_text(json.dumps([asdict(t) for t in self.items], indent=2), encoding=\"utf-8\")\n"
        "        os.replace(tmp, self.path)\n"),
}

MANIFEST = {"schema_version": "1.0", "handoff_id": "HO-0001", "task_id": "TASK-0001", "task_revision": 1,
            "attempt_id": ATT, "outcome": "complete", "summary": "Todo model and atomic JSON store.",
            "completed_items": ["Todo dataclass", "TodoStore add/complete/remove/save"], "unresolved_items": [],
            "assumptions": ["Ids are 8 hex characters"], "decision_requests": [],
            "validation_claims": ["Round-trip works (not run)"],
            "recommended_next_action": "QA writes the core tests."}

OWNER_IDS = {"agent-core-dev": "core_dev", "agent-cli-dev": "cli_dev", "agent-qa": "qa"}
OWNER_NAMES = {"agent-core-dev": "Core dev", "agent-cli-dev": "CLI dev", "agent-qa": "QA"}
INTRO = ("Here is the plan for Todo CLI: a core package for the model and JSON storage, a thin argparse CLI, and a QA "
         "test suite.\n\n")
HEAD = f"AIWB_ATTEMPT_ID: {ATT}\n\n"


def charter() -> dict:
    return copy.deepcopy(CHARTER)


def block(d: dict, indent: int = 1) -> str:
    return ("<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(d, indent=indent, ensure_ascii=False)
            + "\n<<<AIWB_END_PROJECT_CHARTER>>>")


def man_block(m: dict | None = None) -> str:
    return "<<<AIWB_HANDOFF>>>\n" + json.dumps(m or MANIFEST, indent=1) + "\n<<<AIWB_END_HANDOFF>>>"


def aiwb(files: dict | None = None, fence: str = "````") -> str:
    out: list[str] = []
    for p, c in (files or FILES).items():
        out += [f'<<<AIWB_FILE path="{p}" action="write">>>', fence, c.rstrip("\n"), fence, "<<<AIWB_END_FILE>>>", ""]
    return "\n".join(out)


def rename_owners(d: dict, table: dict) -> dict:
    for t in d["tasks"]:
        t["owner_agent_id"] = table[t["owner_agent_id"]]
    for m in d["architecture"]["modules"]:
        m["owner_agent_id"] = table[m["owner_agent_id"]]
    for fo in d["coordination"]["file_ownership"]:
        fo["agent_id"] = table[fo["agent_id"]]
    return d


def build(out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []

    def add(cid: str, name: str, kind: str, style: str, expect: str, content, ext: str = "txt", note: str = "") -> None:
        fn = f"{cid}_{name}.{ext}"
        if isinstance(content, bytes):
            (out_dir / fn).write_bytes(content)
        else:
            with open(out_dir / fn, "w", encoding="utf-8", newline="") as f:
                f.write(content)
        cases.append({"id": cid, "file": fn, "kind": kind, "style": style, "expect": expect,
                      "source": "reconstructed — typical answer shape of " + style.split(":")[0], "note": note})

    # ------------------------------------------------------------------ charters
    add("C01", "canonical", "charter", "Any chat: exactly as the prompt asks", "accept", INTRO + block(charter()) + "\n")
    add("C02", "markers_around_json_fence", "charter", "ChatGPT: markers with a ```json fence inside", "accept",
        INTRO + "<<<AIWB_PROJECT_CHARTER>>>\n```json\n" + json.dumps(charter(), indent=2)
        + "\n```\n<<<AIWB_END_PROJECT_CHARTER>>>\n")
    add("C03", "json_fence_no_markers", "charter", "ChatGPT: markers dropped, only a ```json block", "accept",
        INTRO + "```json\n" + json.dumps(charter(), indent=2) + "\n```\n\nLet me know if you want more milestones.\n")
    add("C04", "raw_json_only", "charter", "API-style: bare JSON, nothing else", "accept", json.dumps(charter()))
    add("C05", "escaped_markers", "charter", "ChatGPT web copy: Markdown escapes of the markers", "accept",
        INTRO + "\\<\\<\\<AIWB\\_PROJECT\\_CHARTER\\>\\>\\>\n" + json.dumps(charter(), indent=1)
        + "\n\\<\\<\\<AIWB\\_END\\_PROJECT\\_CHARTER\\>\\>\\>\n")
    sm = block(charter()).replace('"summary"', "\u201csummary\u201d").replace('"title"', "\u201ctitle\u201d")
    add("C06", "smart_quotes", "charter", "Rendered-page copy: smart quotes around keys", "accept", INTRO + sm + "\n")
    lines: list[str] = []
    for line in json.dumps(charter(), indent=2).splitlines():
        if line.strip().startswith('"risks"'):
            lines.append("  // risks the user should know about")
        lines.append(line)
    txt = "\n".join(lines)
    txt = txt.replace('"Data survives a restart"\n', '"Data survives a restart",\n', 1)
    txt = re.sub(r'("Should completed todos be kept or deleted\?")\n(\s*)\]', r"\1,\n\2]", txt)
    add("C07", "comments_trailing_commas", "charter", "DeepSeek/Gemini: // comments and trailing commas", "accept",
        INTRO + "<<<AIWB_PROJECT_CHARTER>>>\n" + txt + "\n<<<AIWB_END_PROJECT_CHARTER>>>\n")
    d = charter()
    d["schema_version"] = 1
    d["base_state_revision"] = "2"
    add("C08", "numeric_schema_string_revision", "charter", "GPT: schema_version 1, revision as text", "accept",
        INTRO + block(d) + "\n")
    d = rename_owners(charter(), OWNER_IDS)
    d["team"] = {"pm_counted": True, "total_agents": 4, "parallel_chats": 3, "rationale": "core first, then CLI and QA",
                 "agents": [{"agent_id": "pm", "role": "manager", "name": "Project manager", "purpose": "plans"},
                            {"agent_id": "core_dev", "role": "developer", "name": "Core dev", "purpose": "core"},
                            {"agent_id": "cli_dev", "role": "engineer", "name": "CLI dev", "purpose": "cli"},
                            {"agent_id": "qa", "role": "tester", "name": "QA", "purpose": "tests"}]}
    add("C09", "team_with_role_synonyms_short_ids", "charter",
        "GPT: writes the team anyway, roles developer/tester, ids core_dev", "accept", INTRO + block(d) + "\n")
    d = charter()
    d["roadmap"]["milestones"][0]["version"] = "v0.1"
    d["roadmap"]["milestones"][1]["version"] = "v0.2"
    add("C10", "short_versions", "charter", "Claude/GPT: versions v0.1 and v0.2", "accept", INTRO + block(d) + "\n")
    add("C11", "owner_names_not_ids", "charter", "Gemini: owners written as the AI names", "accept",
        INTRO + block(rename_owners(charter(), OWNER_NAMES)) + "\n")
    d = charter()
    for t in d["tasks"]:
        t["acceptance_criteria"] = "; ".join(t["acceptance_criteria"])
        t["scope"] = t["scope"]["include"][0]
    d["risks"] = d["risks"][0]
    d["questions_for_user"] = d["questions_for_user"][0]
    add("C12", "strings_instead_of_lists", "charter", "Copilot: single strings where lists are expected", "accept",
        INTRO + block(d) + "\n")
    d = charter()
    d["tasks"] = {t.pop("ref"): t for t in d["tasks"]}
    add("C13", "tasks_as_dictionary", "charter", "DeepSeek: tasks keyed by ref", "accept", INTRO + block(d) + "\n")
    d = charter()
    tasks = d.pop("tasks")
    for m in d["roadmap"]["milestones"]:
        m["tasks"] = [{k: v for k, v in t.items() if k != "milestone_ref"} for t in tasks
                      if t["milestone_ref"] == m["ref"]]
    add("C14", "tasks_inside_milestones", "charter", "Gemini: tasks nested in their milestone", "accept",
        INTRO + block(d) + "\n")
    d = charter()
    del d["coordination"]
    add("C15", "no_coordination", "charter", "Short answer: coordination left out", "accept", INTRO + block(d) + "\n")
    d = charter()
    del d["coordination"]["sync_points"]
    d["coordination"]["file_ownership"][0]["paths"] = ["src/**"]
    add("C16", "overlap_no_sync_points", "charter", "GPT: src/** for one AI overlaps another, no sync_points",
        "accept", INTRO + block(d) + "\n")
    d = charter()
    d["start_prompts"] = {"agent-core-dev": "You build src/todo.", "agent-cli-dev": "You build src/cli.",
                          "agent-qa": "You write tests."}
    add("C17", "start_prompts_dictionary", "charter", "Older v1 habit: start_prompts as a dictionary", "accept",
        INTRO + block(d) + "\n")
    add("C18", "wrapped_object", "charter", 'Copilot: {"charter": {...}} wrapper', "accept",
        INTRO + "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps({"charter": charter()}, indent=1)
        + "\n<<<AIWB_END_PROJECT_CHARTER>>>\n")
    d = charter()
    for t in d["tasks"]:
        t["id"] = t.pop("ref")
        t["assignee"] = t.pop("owner_agent_id")
        t["depends_on"] = t.pop("depends_on_refs")
        t["description"] = t.pop("objective")
    add("C19", "key_synonyms", "charter", "Claude: id/assignee/depends_on/description keys", "accept",
        INTRO + block(d) + "\n")
    g = ("**Project Charter — Todo CLI**\r\n\r\nBelow\u00a0is the full charter.\r\n\r\n```json\r\n"
         + json.dumps(charter(), indent=2).replace("\n", "\r\n") + "\r\n```\r\n\r\n*Tip: start with the core.*\r\n")
    add("C20", "gemini_crlf_nbsp_bold", "charter", "Gemini web copy: bold title, CRLF, NBSP", "accept", g)
    add("C21", "deepseek_thinking_with_braces", "charter", "DeepSeek: reasoning text with braces before the block",
        "accept", 'Thinking... The user wants a charter. I will use {"ref": "t1"} style refs and keep it short.\n\n'
        "Okay, here is the charter:\n\n" + block(charter()) + "\n")
    add("C22", "copilot_bold_markers", "charter", "Copilot: markers in bold, footnotes", "accept",
        "Sure! Here's a project charter for your Todo CLI [1].\n\n**<<<AIWB_PROJECT_CHARTER>>>**\n```json\n"
        + json.dumps(charter(), indent=2) + "\n```\n**<<<AIWB_END_PROJECT_CHARTER>>>**\n\n[1]: based on your goal\n")
    d = charter()
    d["tasks"][0]["parallel_group"] = None
    d["tasks"][0]["blocking"] = True
    py = json.dumps(d, indent=1).replace("null", "None").replace("true", "True")
    add("C23", "python_literals", "charter", "GPT (Python habit): None/True literals", "accept",
        "<<<AIWB_PROJECT_CHARTER>>>\n" + py + "\n<<<AIWB_END_PROJECT_CHARTER>>>\n")
    d = charter()
    d["roadmap"]["milestones"] = {m.pop("ref"): m for m in d["roadmap"]["milestones"]}
    d["tasks"][0]["priority"] = "P1"
    add("C24", "milestones_dict_priority_p1", "charter", "DeepSeek: milestones keyed by ref, priority P1", "accept",
        INTRO + block(d) + "\n")
    add("C25", "claude_prose_and_bash_block", "charter", "Claude: notes, the block, then a bash example", "accept",
        INTRO + "A few notes before the block:\n\n- The core API is frozen after m1.\n- QA starts after t1.\n\n"
        + block(charter(), indent=2) + '\n\nTo try the CLI later:\n\n```bash\npython -m cli add "buy milk"\n'
        "python -m cli list\n```\n")
    full = block(charter(), indent=2)
    add("C26", "cut_off", "charter", "Any chat: answer stopped by the length limit", "continue",
        INTRO + full[: int(len(full) * 0.6)])
    d = charter()
    d["tasks"][1]["depends_on_refs"] = ["t9"]
    add("C27", "unknown_dependency", "charter", "Any chat: a dependency on a task that does not exist", "fix_prompt",
        INTRO + block(d) + "\n")
    d = charter()
    d["tasks"][2]["owner_agent_id"] = "agent-designer"
    add("C28", "owner_outside_team", "charter", "GPT: invents an AI the user did not define", "fix_prompt",
        INTRO + block(d) + "\n")
    d = charter()
    d["roadmap"]["milestones"][0]["title"] = "Core storage — ذخیره"
    d["project"]["summary"] += " خلاصهٔ فارسی."
    add("C29", "persian_text", "charter", "Any chat answering a Persian user: Persian inside strings", "accept",
        "این برنامهٔ پروژه است:\n\n" + block(d) + "\n")
    html = block(charter()).replace("<<<", "&lt;&lt;&lt;").replace(">>>", "&gt;&gt;&gt;")
    add("C30", "html_entities", "charter", "Copy from an HTML export: &lt;&lt;&lt; markers", "accept",
        INTRO + html + "\n")

    # ------------------------------------------------------------------ files (TASK-0001, scope src/todo/**)
    add("F01", "canonical_aiwb", "files", "Any chat: AIWB blocks + manifest as asked", "accept",
        HEAD + aiwb() + man_block() + "\n")
    add("F02", "aiwb_three_backticks", "files", "GPT: three-backtick fences inside the blocks", "accept",
        HEAD + aiwb(fence="```") + man_block() + "\n")
    esc = ((HEAD + aiwb() + man_block()).replace("<<<", "\\<\\<\\<").replace(">>>", "\\>\\>\\>")
           .replace("AIWB_", "AIWB\\_").replace("END_", "END\\_"))
    add("F03", "escaped_markers", "files", "ChatGPT web copy: escaped markers everywhere", "accept", esc + "\n")
    add("F04", "outer_text_fence", "files", "Gemini: the whole answer inside one ```text fence", "accept",
        "Here is the complete delivery:\n\n`````text\n" + HEAD + aiwb() + man_block() + "\n`````\n")
    md = "Sure! Here are the three files for the core.\n\n"
    for p, c in FILES.items():
        md += f"**{p}**\n```python\n{c}```\n\n"
    add("F05", "markdown_bold_paths", "files", "ChatGPT: **path** + code block, no manifest", "accept",
        md + "Let me know if you need tests.\n")
    md = "## Core implementation\n\n"
    for p, c in FILES.items():
        md += f"### {p}\n\n```python\n{c}```\n\n"
    add("F06", "markdown_headings", "files", "Claude: ### path headings", "accept", md)
    md = "Files:\n\n"
    for p, c in FILES.items():
        md += f"`{p}`:\n```python\n{c}```\n"
    add("F07", "markdown_backtick_paths", "files", "Copilot: `path`: + block", "accept", md)
    md = ""
    for p, c in FILES.items():
        md += f"File: {p}\n```python\n{c}```\n\n"
    add("F08", "markdown_file_label", "files", "DeepSeek: File: path", "accept", HEAD + md)
    md = "Here you go:\n\n"
    for p, c in FILES.items():
        md += f"```python\n# {p}\n{c}```\n\n"
    add("F09", "markdown_path_comment", "files", "GPT: path as the first comment line", "accept", md)
    js = {"attempt_id": ATT, "files": [{"path": p, "content": c} for p, c in FILES.items()], "handoff": dict(MANIFEST)}
    add("F10", "strict_json", "files", "Strict JSON as the prompt asks", "accept", json.dumps(js, indent=1))
    add("F11", "strict_json_fenced_with_prose", "files", "GPT: prose + ```json block", "accept",
        "Below is the JSON you asked for.\n\n```json\n" + json.dumps(js, indent=2) + "\n```\n")
    add("F12", "json_files_dictionary", "files", "Gemini: files as {path: content}", "accept",
        json.dumps({"attempt_id": ATT, "files": dict(FILES), "summary": "core done"}, indent=1))
    add("F13", "json_filename_code_keys", "files", "DeepSeek: filename/code keys", "accept",
        json.dumps({"files": [{"filename": p, "code": c} for p, c in FILES.items()],
                    "handoff": {"summary": "core", "outcome": "complete"}}, indent=1))
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for p, c in FILES.items():
            z.writestr(zipfile.ZipInfo("todo-cli/" + p, (2026, 10, 22, 12, 0, 0)), c)
        z.writestr(zipfile.ZipInfo("todo-cli/AIWB_HANDOFF.json", (2026, 10, 22, 12, 0, 0)), json.dumps(MANIFEST))
    add("F14", "gpt_zip_top_folder", "files", "ChatGPT ZIP: one top folder + AIWB_HANDOFF.json", "accept",
        b.getvalue(), ext="zip")
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for p, c in FILES.items():
            z.writestr(zipfile.ZipInfo(p, (2026, 10, 22, 12, 0, 0)), c)
        z.writestr(zipfile.ZipInfo("__MACOSX/src/todo/._model.py", (2026, 10, 22, 12, 0, 0)), "x")
        z.writestr(zipfile.ZipInfo(".DS_Store", (2026, 10, 22, 12, 0, 0)), "x")
    add("F15", "zip_flat_with_noise", "files", "ZIP made on a Mac: flat, __MACOSX and .DS_Store", "accept",
        b.getvalue(), ext="zip")
    w = ((HEAD + aiwb() + man_block()).replace("\n", "\r\n").replace("<<<AIWB_FILE path", "<<<AIWB_FILE\u00a0path")
         .replace("<<<AIWB_END_FILE>>>", "<<<AIWB_END_FILE>>>\u200b"))
    add("F16", "crlf_nbsp_zero_width", "files", "Windows clipboard: CRLF, NBSP and zero-width characters", "accept", w)
    sq = (HEAD + aiwb() + man_block()).replace('path="', "path=\u201c").replace('" action="write"',
                                                                                "\u201d action=\u201cwrite\u201d")
    add("F17", "smart_quoted_attributes", "files", 'Rendered copy: smart quotes in path="…"', "accept", sq + "\n")
    md = "Here's the core implementation.\n\n"
    for p, c in FILES.items():
        md += f"#### `{p}`\n```python\n{c}```\n"
    add("F18", "gemini_heading_code_paths", "files", "Gemini: #### `path` headings", "accept", md)
    parts = [HEAD + "I kept the API small.\n"]
    for p, c in FILES.items():
        parts.append(f"Next, `{p}`:\n" + aiwb({p: c}))
    add("F19", "claude_prose_between_blocks", "files", "Claude: explanation between the AIWB blocks", "accept",
        "\n".join(parts) + man_block() + "\n")
    full = HEAD + aiwb()
    add("F20", "cut_off_aiwb", "files", "Any chat: stopped in the middle of the last file", "continue",
        full[: full.rfind("os.replace")])
    oos = dict(FILES)
    oos["src/cli/main.py"] = "print('cli')\n"
    add("F21", "file_outside_scope", "files", "GPT: also writes a file of another AI", "fix_prompt",
        HEAD + aiwb(oos) + man_block() + "\n")
    md = ""
    for p, c in FILES.items():
        md += f'```python title="{p}"\n{c}```\n\n'
    add("F22", "info_string_title", "files", 'DeepSeek/Docs style: ```python title="path"', "accept",
        "Implementation:\n\n" + md)
    md = "Sure, here they are:\n\n"
    for p, c in FILES.items():
        md += f"**File: `{p}`**\n\n```python\n{c}```\n\n"
    add("F23", "bold_file_label_code_path", "files", "Copilot: **File: `path`**", "accept", md)
    add("F24", "bare_path_line", "files", "Plain copy of a rendered answer: the path alone on a line", "accept",
        HEAD + "".join(f"{p}\n```python\n{c}```\n\n" for p, c in FILES.items()) + "Done.\n")

    with open(out_dir / "corpus.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"schema": "aiwb-answer-corpus.v1", "scenario": "tests/answer_corpus.py",
                   "built_by": "tests/fixtures/answers/build_corpus.py", "cases": cases}, f, indent=1,
                  ensure_ascii=False)
        f.write("\n")
    return cases


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.path.dirname(os.path.abspath(__file__)))
    print(len(build(target)), "cases written to", target)
