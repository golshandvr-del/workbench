"""Roadmap 5.12.0 (owner audit B2): a context request is a real step, not a dead end.

Owner's test of 5.11.0: GPT answered the task prompt with an AIWB_CONTEXT_REQUEST; the paste box said "✓" and then
nothing happened. Now, driven only through the guide (the same calls as the Home card):

  task prompt → paste the request → card "<AI> asked for N files" → Copy the files for the chat (text with the
  files, attempt line, folder expanded, secrets refused) → I sent them → Paste the answer → the delivery is read and
  the request is closed.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2.context_step import is_sensitive  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"
OWNER = REPO / "docs/audit/owner-5.11/HO-0006_gpt_answer_context_request.txt"


def charter_block(data: dict) -> str:
    return "<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(data) + "\n<<<AIWB_END_PROJECT_CHARTER>>>\n"


def request_like_gpt(attempt_id: str, paths: list[str]) -> str:
    """The shape GPT really wrote (owner audit B2): no "type", "required_files", a folder."""
    body = {"schema_version": "1.0", "attempt_id": attempt_id, "handoff_id": "HO-x",
            "required_files": [{"path": p, "mode": "full_file", "reason": "needed"} for p in paths],
            "reason": "The handoff names files it does not include.",
            "requested_action": "Return the requested file contents."}
    return (f"AIWB_ATTEMPT_ID: {attempt_id}\n\n<<<AIWB_CONTEXT_REQUEST>>>\n" + json.dumps(body, indent=2)
            + "\n<<<AIWB_END_CONTEXT_REQUEST>>>")


def windows_copy(text: str) -> str:
    """What selecting the rendered answer and pressing Ctrl+C gives on Windows (owner audit B1)."""
    return "\n".join(line + "\\" if line.strip() else line for line in text.split("\n"))


class ContextStepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "src" / "contracts").mkdir(parents=True)
        (self.root / "src" / "contracts" / "models.py").write_text("class Model:\n    pass\n", encoding="utf-8")
        (self.root / "src" / "bridge").mkdir(parents=True)
        (self.root / "src" / "bridge" / "a.py").write_text("A = 1\n", encoding="utf-8")
        (self.root / "src" / "bridge" / "b.py").write_text("B = 2\n", encoding="utf-8")
        (self.root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
        self.c = ProjectsController(self.root, make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        self.g.perform("design", "design", goal="An offline todo app")
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["base_state_revision"] = self.c.state()["state_revision"]
        out = self.g.perform("charter", "paste", text=charter_block(data))
        self.assertEqual(out["kind"], "proposal", out["message"])
        self.g.perform(self.g.steps()[0]["key"], "accept")
        step = next(s for s in self.g.steps() if s["key"].startswith("task:")
                    and any(a["id"] == "prepare" for a in s["actions"]))
        self.h = self.g.perform(step["key"], "prepare")
        self.hid = self.h["handoff_id"]
        self.g.perform(f"handoff:{self.hid}", "copy")
        self.att = self.c.state()["handoffs"][self.hid]["attempt_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def step(self) -> dict:
        return next(s for s in self.g.steps() if s["key"] == f"handoff:{self.hid}")

    def test_task_prompt_shows_the_exact_request_format(self):
        p = self.h["prompt"]
        self.assertIn("<<<AIWB_CONTEXT_REQUEST>>>", p)
        self.assertIn('"type": "AIWB_CONTEXT_REQUEST"', p)
        self.assertIn('"files": [', p)

    def test_request_turns_the_card_into_the_files_step_and_back(self):
        text = request_like_gpt(self.att, ["src/contracts/models.py", "src/bridge/", ".env", "src/nope.py"])
        out = self.g.perform(f"handoff:{self.hid}", "paste", text=text)
        self.assertEqual(out["kind"], "context_request", out["message"])
        self.assertEqual(out["handoff_id"], self.hid)
        self.assertIn("Copy the files for the chat", out["message"])
        s = self.step()
        self.assertIn("asked for 4 files", s["title"])
        primary = next(a for a in s["actions"] if a["primary"])
        self.assertEqual(primary["id"], "copy_context")
        self.assertIn("paste", [a["id"] for a in s["actions"]], "the answer box stays on the card")

        pack = self.g.perform(f"handoff:{self.hid}", "copy_context")
        text = pack["prompt"]
        self.assertTrue(text.startswith(f"AIWB_ATTEMPT_ID: {self.att}"))
        self.assertIn("class Model:", text)
        self.assertIn("src/bridge/a.py", text)          # the folder became its files
        self.assertIn("src/bridge/b.py", text)
        self.assertNotIn("TOKEN=secret", text)           # secrets are never packed
        self.assertIn(".env: refused_sensitive", text)
        self.assertIn("src/nope.py: missing", text)
        self.assertEqual(sorted(pack["context_files"]),
                         ["src/bridge/a.py", "src/bridge/b.py", "src/contracts/models.py"])

        s = self.step()
        self.assertEqual(next(a for a in s["actions"] if a["primary"])["id"], "context_sent")
        self.g.perform(f"handoff:{self.hid}", "context_sent")
        s = self.step()
        self.assertEqual(s["kind"], "paste")
        self.assertEqual(next(a for a in s["actions"] if a["primary"])["id"], "paste")

        h = self.c.state()["handoffs"][self.hid]
        scope = (self.c.state()["tasks"][h["task_id"]]["scope"]["include"] or ["src/**"])[0].rstrip("*").rstrip("/")
        answer = (f"AIWB_ATTEMPT_ID: {self.att}\n<<<AIWB_FILE path=\"{scope}/done.txt\" action=\"write\">>>\nok\n"
                  "<<<AIWB_END_FILE>>>\n<<<AIWB_HANDOFF>>>\n" + json.dumps(
                      {"schema_version": "1.0", "handoff_id": self.hid, "task_id": h["task_id"],
                       "task_revision": h["task_revision"], "attempt_id": self.att, "outcome": "complete",
                       "summary": "done", "completed_items": ["done"], "unresolved_items": [],
                       "validation_claims": []}) + "\n<<<AIWB_END_HANDOFF>>>")
        out = self.g.perform(f"handoff:{self.hid}", "paste", text=answer)
        self.assertEqual(out["kind"], "handoff", out["message"])
        h = self.c.state()["handoffs"][self.hid]
        self.assertNotIn("context_request", h)
        self.assertEqual(len(h["context_history"]), 1)
        self.assertNotIn("asked for", self.step()["title"])

    def test_owner_answer_copied_from_windows_reaches_the_files_step(self):
        real = OWNER.read_text(encoding="utf-8").replace("\r", "")
        real = real.replace("att-20261023-192855-0ba9959e", self.att)
        out = self.g.perform(f"handoff:{self.hid}", "paste", text=windows_copy(real))
        self.assertEqual(out["kind"], "context_request", out["message"])
        self.assertIn("asked for 4 files", self.step()["title"])

    def test_request_without_attempt_uses_the_card_it_was_pasted_on(self):
        text = request_like_gpt("", ["src/contracts/models.py"])
        out = self.g.perform(f"handoff:{self.hid}", "paste", text=text)
        self.assertEqual(out["kind"], "context_request", out["message"])
        self.assertIn("asked for 1 file", self.step()["title"])

    def test_large_request_becomes_a_zip_to_attach(self):
        big = self.root / "src" / "big"
        big.mkdir()
        for i in range(8):
            (big / f"f{i}.py").write_text(("x = 1  # padding\n" * 600), encoding="utf-8")
        self.g.perform(f"handoff:{self.hid}", "paste", text=request_like_gpt(self.att, ["src/big/"]))
        pack = self.g.perform(f"handoff:{self.hid}", "copy_context")
        self.assertTrue(pack["zip_path"].endswith("-context.zip"), pack["message"])
        self.assertTrue(Path(pack["zip_path"]).is_file())
        self.assertIn("attach", pack["message"])
        self.assertLess(len(pack["prompt"]), 5000)

    def test_sensitive_rule(self):
        for p in (".env", "a/.env.local", "keys/id_rsa", "x.pem", ".workbench/v2/state.json", ".git/config",
                  "secrets/a.txt"):
            self.assertTrue(is_sensitive(p), p)
        for p in ("src/a.py", ".env.example", "README.md", "docs/secrets.md"):
            self.assertFalse(is_sensitive(p), p)


if __name__ == "__main__":
    unittest.main()
