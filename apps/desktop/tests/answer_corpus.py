"""The answer corpus of roadmap 5.10.0: every answer in ``tests/fixtures/answers/`` replayed into a fresh project.

Scenario (deterministic, so stored answers replay exactly):

* the New Project wizard made "Todo CLI" (Python 3.12, Windows) with the team **Project manager · Core dev · CLI dev
  · QA** → state revision 2, agent ids ``agent-core-dev``, ``agent-cli-dev``, ``agent-qa``;
* ``charter`` answers are pasted on the Guide's charter step;
* ``files`` answers are pasted for the first task (TASK-0001, owner Core dev, scope ``src/todo/**``) after the
  canonical charter ``C01`` was accepted and the task prompt prepared, copied and sent. The stored answers carry the
  placeholder attempt id ``ATTEMPT`` below; replay puts the real one in its place (every model repeats the id the prompt
  gave it).

``corpus.json`` lists every case: ``id``, ``file``, ``kind`` (charter | files | context — 5.12.0), ``style`` (which chat app / habit it
imitates), ``source`` and ``expect`` — ``accept`` (charter → proposal; files → linked, staged, no error in the smart
check) or ``fix_prompt`` / ``continue`` (refused, with a prompt the user can send back).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import AI_Workbench as wb
from aiwb.v2 import V2Project
from aiwb.v2 import team_setup as ts
from aiwb.v2.controller import ProjectsController
from aiwb.v2.guide import Guide

HERE = Path(__file__).resolve().parent
ANSWERS = HERE / "fixtures" / "answers"
ATTEMPT = "att-20261022-120000-0a1b2c3d"
TEAM = [{"name": "Project manager", "role": "project_manager", "model": "", "note": ""},
        {"name": "Core dev", "role": "implementer", "model": "", "note": ""},
        {"name": "CLI dev", "role": "implementer", "model": "", "note": ""},
        {"name": "QA", "role": "reviewer", "model": "", "note": ""}]
BRIEF = {"goal": "A command-line todo app in Python with JSON storage", "name": "Todo CLI",
         "platform": "Python 3.12, Windows", "constraints": "standard library only"}


def cases() -> list[dict[str, Any]]:
    return json.loads((ANSWERS / "corpus.json").read_text(encoding="utf-8"))["cases"]


def answer_bytes(case: dict[str, Any]) -> bytes:
    return (ANSWERS / case["file"]).read_bytes()


class Scenario:
    """A fresh project for one case; ``close()`` removes it."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="aiwb-corpus-")
        self.root = Path(self.tmp.name)
        ts.apply_wizard(V2Project(self.root, "p"), BRIEF, TEAM, "aiwb")
        self.c = ProjectsController(self.root, make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)

    def close(self) -> None:
        self.tmp.cleanup()

    def charter_prompt(self) -> str:
        return next(s for s in self.g.steps() if s["key"] == "charter")["prompt"]

    def paste_charter(self, text: str) -> dict[str, Any]:
        return self.g.perform("charter", "paste", text=text)

    def to_first_task(self) -> dict[str, Any]:
        """Accept the canonical charter, prepare/copy/send TASK-0001; returns the handoff step."""
        out = self.paste_charter((ANSWERS / "C01_canonical.txt").read_text(encoding="utf-8"))
        assert out["kind"] == "proposal", out["message"]
        step = next(s for s in self.g.steps() if s["key"].startswith("proposal:"))
        self.g.perform(step["key"], "accept")
        step = next(s for s in self.g.steps() if s["key"] == "task:TASK-0001")
        self.g.perform(step["key"], "prepare")
        step = next(s for s in self.g.steps() if s["key"].startswith("handoff:"))
        self.g.perform(step["key"], "copy")
        self.g.perform(step["key"], "sent")
        return next(s for s in self.g.steps() if s["key"].startswith("handoff:"))

    def attempt_id(self, step: dict[str, Any]) -> str:
        return self.c.project.handoffs.get(step["ref"])["attempt_id"]


def replay(case: dict[str, Any]) -> dict[str, Any]:
    """Paste one corpus answer the way the user would; returns ``{"ok", "kind", "message", "prompt", ...}``."""
    sc = Scenario()
    try:
        raw = answer_bytes(case)
        if case["kind"] == "charter":
            out = sc.paste_charter(raw.decode("utf-8"))
            ok = out["kind"] == "proposal"
            res = {"kind": out["kind"], "message": out["message"], "prompt": out.get("prompt", "")}
            if ok:
                p = next(iter(sc.c.state()["proposals"].values()))
                res["tasks"] = len([o for o in p["operations"] if o["operation"] == "create_task" and o["valid"]])
                res["fixes"] = len(p.get("auto_fixes") or [])
            return {"ok": ok, **res}
        step = sc.to_first_task()
        att = sc.attempt_id(step)
        if case["file"].endswith(".zip"):
            from aiwb.intake.answer_files import canonical_zip
            text, _ex = canonical_zip(raw, name=case["file"])
            text = text.replace(ATTEMPT, att)
        else:
            text = raw.decode("utf-8").replace(ATTEMPT, att)
        out = sc.g.perform(step["key"], "paste", text=text)
        if case["kind"] == "context":
            # 5.12.0 (owner audit B2): a context request is usable when the card turns into the files step and the
            # files can be copied for the chat
            now = next((s for s in sc.g.steps() if s["key"] == step["key"]), {})
            ok = out["kind"] == "context_request" and now.get("actions", [{}])[0].get("id") == "copy_context"
            prompt = ""
            if ok:
                prompt = sc.g.perform(step["key"], "copy_context")["prompt"]
                ok = prompt.startswith(f"AIWB_ATTEMPT_ID: {att}")
            return {"ok": ok, "kind": out["kind"], "message": out["message"], "prompt": prompt, "errors": []}
        errors = [p for p in out.get("problems", []) if p["severity"] == "error"]
        ok = out["kind"] == "handoff" and bool(out.get("staged")) and not errors
        return {"ok": ok, "kind": out["kind"], "message": out["message"], "prompt": out.get("prompt", ""),
                "staged": out.get("staged", []), "errors": [f"{p['code']}: {p['message']}" for p in errors]}
    finally:
        sc.close()
