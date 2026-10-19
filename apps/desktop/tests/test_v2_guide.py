"""Roadmap 3.5.0 gate: guided loop without dead ends.

* Invariant: in every state reached during the scripted runs (and a set of hand-made edge states) the
  guide offers at least one step, every step has at least one action, and prompt steps carry a prompt.
* E2E: idea → Project Charter → 3 AIs working in parallel (scripted answers) → reviews → validation →
  milestones → released versions, driven ONLY through the guide's steps and actions.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import Guide, KINDS  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"


def charter_block(data: dict) -> str:
    return "Here is the charter.\n<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(data) + "\n<<<AIWB_END_PROJECT_CHARTER>>>\n"


def answer_for(h: dict, *, partial: bool = False, cut: bool = False) -> str:
    """A scripted AI: files for the task scope + the handoff manifest."""
    scope = (h.get("_scope") or ["src/x/**"])[0].rstrip("*").rstrip("/")
    files = [f"{scope}/a.txt", f"{scope}/b.txt"]
    body = "".join(f'<<<AIWB_FILE path="{p}" action="write" body="raw">>>\n{p} content\n<<<AIWB_END_FILE>>>\n'
                   for p in files[: 1 if partial else 2])
    if cut:
        return f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n" + body + f'<<<AIWB_FILE path="{scope}/c.txt" action="write">>>\nhalf'
    man = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": h["task_id"],
           "task_revision": h["task_revision"], "attempt_id": h["attempt_id"],
           "outcome": "partial" if partial else "complete", "summary": "delivered " + h["task_id"],
           "completed_items": files[:1] if partial else files,
           "unresolved_items": [f"missing file: {files[1]}"] if partial else [], "validation_claims": ["tests pass"]}
    return f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n" + body + "<<<AIWB_HANDOFF>>>\n" + json.dumps(man) + "\n<<<AIWB_END_HANDOFF>>>\n"


class GuideBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = ProjectsController(Path(self.tmp.name), make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        self.seen_states: list[str] = []

    def tearDown(self):
        self.tmp.cleanup()

    def check_invariant(self):
        steps = self.g.steps()
        self.assertTrue(steps, "dead end: no step")
        for s in steps:
            self.assertIn(s["kind"], KINDS)
            self.assertTrue(s["actions"], f"step without action: {s['key']}")
            self.assertEqual(sum(1 for a in s["actions"] if a["primary"]), 1, s["key"])
            self.assertTrue(s["title"] and s["explain"], s["key"])
            if s["kind"] == "prompt" and any(a["id"] == "copy" for a in s["actions"]):
                self.assertTrue(s["prompt"].strip(), f"prompt step without prompt: {s['key']}")
        self.seen_states.append(",".join(sorted({s["key"].split(":")[0] for s in steps})))
        return steps


class InvariantTests(GuideBase):
    def test_empty_project_asks_for_the_goal_then_offers_the_charter_prompt(self):
        s = self.check_invariant()[0]
        self.assertEqual((s["key"], s["kind"]), ("design", "form"))
        with self.assertRaises(Exception):
            self.g.perform("design", "design", goal="")
        out = self.g.perform("design", "design", goal="An offline todo app")
        self.assertIn("AIWB_PROJECT_CHARTER", out["prompt"])
        s = self.check_invariant()[0]
        self.assertEqual(s["key"], "charter")
        self.assertIn("AIWB_PROJECT_CHARTER", s["prompt"])

    def test_cut_off_answer_gets_a_continue_prompt_and_can_be_dismissed(self):
        self.g.perform("design", "design", goal="An offline todo app")
        out = self.g.perform("charter", "paste", text='<<<AIWB_FILE path="a.py" action="write">>>\nx = ')
        self.assertEqual(out["kind"], "truncated")
        self.assertIn("cut off", out["prompt"])
        s = self.check_invariant()[0]
        self.assertEqual(s["key"], "continue")
        self.g.perform("continue", "dismiss")
        self.assertEqual(self.check_invariant()[0]["key"], "charter")

    def test_incomplete_charter_returns_the_fix_prompt(self):
        self.g.perform("design", "design", goal="An offline todo app")
        bad = json.loads(FIXTURE.read_text(encoding="utf-8"))
        del bad["tasks"]
        out = self.g.perform("charter", "paste", text=charter_block(bad))
        self.assertEqual(out["kind"], "charter_rejected")
        self.assertIn("tasks", out["prompt"])
        self.check_invariant()

    def test_nothing_waiting_offers_the_manager_update_with_the_continue_question(self):
        t = self.c.project.tasks.create({"title": "A", "objective": "a", "owner_agent_id": "agent-implementer"})
        self.c.project.tasks.transition(t["task_id"], "cancelled", "test")
        s = self.check_invariant()[-1]
        self.assertEqual(s["key"], "manager_update")
        self.assertIn("Propose the next step", s["prompt"])
        self.g.perform("manager_update", "copy")
        self.g.perform("manager_update", "sent")
        self.assertEqual(self.check_invariant()[-1]["title"], "Ask the project manager for the next step")

    def test_blocked_and_needs_decision_tasks_have_a_way_out(self):
        p = self.c.project
        a = p.tasks.create({"title": "A", "objective": "a", "owner_agent_id": "agent-implementer"})
        p.tasks.transition(a["task_id"], "blocked", "the API is gone")
        b = p.tasks.create({"title": "B", "objective": "b", "owner_agent_id": "agent-implementer"})
        p.tasks.transition(b["task_id"], "needs_decision", "JSON or SQLite?")
        keys = {s["key"]: s for s in self.check_invariant()}
        self.assertIn("unblock", [x["id"] for x in keys[f"task:{a['task_id']}"]["actions"]])
        self.g.perform(f"task:{b['task_id']}", "decide", choice="JSON", rationale="simple")
        self.assertEqual(p.tasks.get(b["task_id"])["status"], "ready")
        self.g.perform(f"task:{a['task_id']}", "unblock")
        self.assertEqual(p.tasks.get(a["task_id"])["status"], "ready")
        self.check_invariant()

    def test_action_not_offered_is_refused(self):
        with self.assertRaises(Exception):
            self.g.perform("design", "accept")


class EndToEndTests(GuideBase):
    def test_idea_to_released_versions_with_three_parallel_ais(self):
        c, g = self.c, self.g
        # 1. idea → charter prompt → scripted manager answer
        g.perform("design", "design", goal="An offline todo app for desktop and mobile")
        self.check_invariant()
        g.perform("charter", "copy")
        g.perform("charter", "sent")
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["base_state_revision"] = c.state()["state_revision"]
        out = g.perform("charter", "paste", text=charter_block(data))
        self.assertEqual(out["kind"], "proposal", out["message"])
        step = self.check_invariant()[0]
        self.assertTrue(step["key"].startswith("proposal:"))
        g.perform(step["key"], "accept")
        st = c.state()
        self.assertEqual(len(st["tasks"]), 3)
        self.assertEqual(len(st["versions"]), 2)
        scope = {t["task_id"]: t["scope"]["include"] for t in st["tasks"].values()}

        partial_done, cut_done = False, False
        parallel_seen = 0
        for _ in range(200):
            steps = self.check_invariant()
            q = g.queues()
            parallel_seen = max(parallel_seen, sum(1 for a, ss in q.items()
                                                   if a not in ("you", "agent-project-manager")
                                                   and any(s["key"].startswith("handoff:") for s in ss)))
            if all(v["status"] == "released" for v in c.state()["versions"].values()):
                break
            # prefer AI prompt steps first so that several AIs work at the same time
            step = next((s for s in steps if s["key"].startswith("task:") and s["actions"][0]["id"] == "prepare"), steps[0])
            key, first = step["key"], next(a["id"] for a in step["actions"] if a["primary"])
            if key.startswith("handoff:") and step["kind"] in ("prompt", "paste"):
                h = dict(c.project.handoffs.get(step["ref"]))
                h["_scope"] = scope[h["task_id"]]
                if first == "copy":
                    g.perform(key, "copy")
                elif first == "sent":
                    g.perform(key, "sent")
                else:
                    others = [s for s in steps if s["key"].startswith("handoff:") and s["kind"] == "paste"]
                    if len(others) < 2 and not partial_done and any(
                            s["key"].startswith("task:") and s["actions"][0]["id"] == "prepare" for s in steps):
                        continue
                    if not cut_done:
                        cut_done = True
                        r = g.perform(key, "paste", text=answer_for(h, cut=True))
                        self.assertEqual(r["kind"], "truncated")
                        self.assertEqual(self.check_invariant()[0]["key"], "continue")
                        g.perform("continue", "dismiss")
                        continue
                    if not partial_done:
                        partial_done = True
                        r = g.perform(key, "paste", text=answer_for(h, partial=True))
                        self.assertEqual(r["kind"], "handoff", r["message"])
                        rs = next(s for s in self.check_invariant() if s["key"] == key)
                        self.assertIn("repair", [a["id"] for a in rs["actions"]])
                        r = g.perform(key, "repair")
                        self.assertIn("Arrived complete", r["prompt"])
                        self.assertNotIn("missing file: " + "x", r["prompt"].split("Still missing")[0])
                        continue
                    r = g.perform(key, "paste", text=answer_for(h))
                    self.assertEqual(r["kind"], "handoff", r["message"])
                continue
            if key.startswith("task:") and first == "prepare":
                g.perform(key, "prepare")
                continue
            if key.startswith("handoff:"):
                g.perform(key, "accept_handoff")
                continue
            if key.startswith("task:") and first == "approve":
                rp = g.perform(key, "review_prompt")
                self.assertIn("VERDICT", rp["prompt"])
                g.perform(key, "approve")
                continue
            if key.startswith("task:") and first == "record_validation":
                g.perform(key, "record_validation", result="passed", run_id="run-" + step["ref"])
                continue
            if key.startswith("milestone:"):
                g.perform(key, "accept_milestone")
                continue
            if key.startswith("version:"):
                g.perform(key, "release", commit_sha="a" * 40, tag="", run_id="run-rel-" + step["ref"])
                continue
            self.fail(f"scripted user does not know step {key} / {first}: {step['title']}")
        st = c.state()
        self.assertTrue(all(t["status"] == "done" for t in st["tasks"].values()), [t["status"] for t in st["tasks"].values()])
        self.assertEqual(sorted(v["status"] for v in st["versions"].values()), ["released", "released"])
        self.assertTrue(all(m["status"] == "accepted" for m in st["milestones"].values()))
        self.assertTrue(partial_done and cut_done)
        self.assertGreaterEqual(parallel_seen, 2, "the two UI AIs had open prompts at the same time")
        self.assertEqual(self.check_invariant()[-1]["key"], "manager_update")


if __name__ == "__main__":
    unittest.main()
