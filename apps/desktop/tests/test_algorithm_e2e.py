"""Roadmap 4.7.0 gate (desktop half): the whole owner's algorithm, end to end, through the Guide only.

Three scripted AIs work in parallel (core, desktop, mobile) under a scripted project manager. The walk visits every
edge of ``project-flow.v1`` — 32 edges, including troubleshooting (F13 no → F14 → F15 → F11), the emergency branch
(F21 yes → F10), the release (F23 yes → F24), "no release needed" (F23 no → F25), the next stage (F25 yes → F10),
completion (F25 no → F26), expansion (F27 yes → F1) and archive (F27 no → F28).

Each edge is *observed*, never assumed: the test records the flowchart node (``flow.current``) and the timeline
events after every user action, and an edge counts only when its own evidence was seen. At the end every edge of the
shared fixture must be covered. The phone runs the same walk in ``AlgorithmE2ETest.kt``.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2 import ModelError, flow  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import Guide  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FLOW = REPO / "packages/contracts/fixtures/flow/project-flow.v1.json"
CHARTER = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"
F4 = "````"


class AlgorithmWalk(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = ProjectsController(self.root, make_pipeline=wb.make_inbox_pipeline)
        self.g = Guide(self.c)
        self.edges: set[tuple[str, str]] = set()
        self.nodes: list[str] = []
        self.seen = 0

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # -- observation ----------------------------------------------------------------------------------
    def node(self) -> str:
        return self.g.flow()["node"]

    def events(self) -> list[str]:
        ev = self.c.state()["events"]
        out = [e["type"] for e in ev[self.seen:]]
        self.seen = len(ev)
        return out

    def edge(self, a: str, b: str, ok: bool = True) -> None:
        self.assertTrue(ok, f"no evidence for edge {a} -> {b}")
        self.edges.add((a, b))

    def at(self, expected: str) -> None:
        self.assertEqual(self.node(), expected)
        self.nodes.append(expected)

    # -- scripted chats -------------------------------------------------------------------------------
    def keys(self) -> list[str]:
        return [s["key"] for s in self.g.steps()]

    def do(self, key: str, action: str, **inp: str) -> dict:
        return self.g.perform(key, action, **inp)

    def hstep(self, tid: str) -> str:
        return next(s["key"] for s in self.g.steps() if s["key"].startswith("handoff:") and s.get("task_id") == tid)

    def answer(self, tid: str, files: list[str], bad: bool = False) -> str:
        h = next(h for h in self.c.state()["handoffs"].values()
                 if h["task_id"] == tid and h["status"] in ("prepared", "prompt_exported"))
        man = {"schema_version": "1.0", "handoff_id": h["handoff_id"], "task_id": tid, "task_revision": h["task_revision"],
               "attempt_id": h["attempt_id"], "outcome": "complete", "summary": "done", "completed_items": ["x"],
               "unresolved_items": [], "validation_claims": ["all tests pass"]}
        body = "".join(f'<<<AIWB_FILE path="{p}" action="write">>>\n{F4}\nX = 1\n{F4}\n<<<AIWB_END_FILE>>>\n'
                       for p in (["../outside.py"] if bad else files))
        return (f"AIWB_ATTEMPT_ID: {h['attempt_id']}\n" + body + "<<<AIWB_HANDOFF>>>\n" + json.dumps(man)
                + "\n<<<AIWB_END_HANDOFF>>>\n")

    def plan(self, ops: list[dict], remaining: bool, emergency: list | None = None) -> str:
        body = {"schema_version": "1.0", "base_state_revision": self.c.state()["state_revision"], "summary": "next",
                "operations": ops, "roadmap_remaining": remaining, "emergency_tasks": emergency or []}
        return "Status read.\n<<<AIWB_MANAGER_PROPOSAL>>>\n" + json.dumps(body) + "\n<<<AIWB_END_MANAGER_PROPOSAL>>>"

    def deliver(self, tid: str, files: list[str]) -> None:
        """F11 → F12 → F13 yes → F16 → F17 for one task: copy, send, paste a good answer, accept, review, verify."""
        k = self.hstep(tid)
        self.do(k, "copy")
        self.do(k, "sent")
        self.do(k, "paste", text=self.answer(tid, files))
        self.assertTrue(self.c.state()["handoffs"][k.split(":", 1)[1]].get("staged_files"))
        self.do(k, "accept_handoff")
        self.do(f"task:{tid}", "approve")
        self.do(f"task:{tid}", "validation_passed", run_id=f"ci-{tid}")
        self.assertEqual(self.c.state()["tasks"][tid]["status"], "done")

    def report(self, ops: list[dict], remaining: bool, emergency: list | None = None) -> dict:
        """F18 → F19 → F20 → F21: status prompt to the manager, its decision pasted and accepted."""
        self.at("F18")
        k = "manager_update"
        step = self.g.find(k)
        self.assertIn("roadmap_remaining", step["prompt"])
        self.do(k, "copy")
        self.edge("F18", "F19", "manager_copied_at" in self.c.state()["settings"]["guide"])
        self.do(k, "sent")
        self.edge("F19", "F20", "manager_sent_at" in self.c.state()["settings"]["guide"])
        out = self.do(k, "paste", text=self.plan(ops, remaining, emergency))
        self.assertEqual(out["kind"], "proposal", out["message"])
        self.at("F21")
        self.edge("F20", "F21")
        pid = next(s["ref"] for s in self.g.steps() if s["key"].startswith("proposal:"))
        self.do(f"proposal:{pid}", "accept")
        return self.c.state()["settings"]["flow"]["last_decision"]

    # -- the walk -------------------------------------------------------------------------------------
    def test_every_edge_of_the_flowchart(self) -> None:  # noqa: C901 — one scripted story
        c, g = self.c, self.g
        # F1 → F2, F3, F4: the start form starts the timeline once and binds the repository (manual GitHub)
        self.at("F1")
        self.do("design", "design", goal="An offline todo app for desktop and mobile", name="Todo", ais="3")
        ev = self.events()
        self.edge("F1", "F2", ev.count("project_started") == 1)
        self.edge("F1", "F4", c.state()["settings"]["team"]["max_parallel_chats"] == 3)
        self.do("github:connect", "prepare_connect", owner="o", name="todo")
        self.do("github:connect", "record", owner="o", name="todo")
        self.edge("F1", "F3", c.state()["settings"]["flow"]["repo"]["branch"] == "aiwb/todo" and "github_connect" in self.events())
        # F4 → F5 → F6 → F7 → F8
        self.at("F5")
        self.edge("F4", "F5", "AIWB_PROJECT_CHARTER" in g.find("charter")["prompt"])
        self.do("charter", "copy")
        self.at("F6")
        self.edge("F5", "F6")
        self.do("charter", "sent")
        self.at("F7")
        self.edge("F6", "F7")
        data = json.loads(CHARTER.read_text(encoding="utf-8"))
        data["base_state_revision"] = c.state()["state_revision"]
        self.do("charter", "paste", text="<<<AIWB_PROJECT_CHARTER>>>\n" + json.dumps(data) + "\n<<<AIWB_END_PROJECT_CHARTER>>>")
        self.at("F8")
        self.edge("F7", "F8")
        self.assertEqual(c.state()["tasks"], {}, "nothing is created before the user checks the charter")
        # F8 → F9 → F10: the charter becomes three parallel paths with dependencies (core first, then 2 UIs)
        self.do(self.keys()[0], "accept")
        st = c.state()
        core, desk, mob = sorted(st["tasks"])
        self.edge("F8", "F9", "charter_accepted" in self.events() and len(st["tasks"]) == 3)
        self.at("F10")
        self.edge("F9", "F10", st["tasks"][core]["status"] == "ready" and st["tasks"][desk]["status"] == "blocked")
        # F10 → F11 → F12 → F13 no → F14 → F15 → F11: the core AI's first answer writes outside the project
        self.do(f"task:{core}", "prepare")
        self.at("F11")
        self.edge("F10", "F11", "handoff_prepared" in self.events())
        k = self.hstep(core)
        self.do(k, "copy")
        self.do(k, "sent")
        self.at("F12")
        self.edge("F11", "F12", "user_confirmed_sent" in self.events())
        out = self.do(k, "paste", text=self.answer(core, [], bad=True))
        self.assertIn("unsafe_path", out["message"])
        self.at("F13")
        self.edge("F12", "F13", "handoff_ingested" in self.events())
        step = g.find(self.hstep(core))
        self.edge("F13", "F14", step["actions"][0]["id"] == "troubleshoot" and step.get("problems"))
        out = self.do(step["key"], "troubleshoot")
        self.edge("F14", "F15", "[unsafe_path]" in out["prompt"] and "troubleshooting_prompt" in self.events())
        self.at("F11")
        self.edge("F15", "F11")
        # second try is good: F13 yes → F16 → F17
        k = self.hstep(core)
        self.do(k, "sent")
        self.do(k, "paste", text=self.answer(core, ["src/core/todo.py"]))
        self.at("F13")
        self.do(k, "accept_handoff")
        self.at("F16")
        ev = self.events()
        self.edge("F13", "F16", "handoff_accepted" in ev)
        self.edge("F16", "F17", "files_integrated" in ev and (self.root / "src/core/todo.py").is_file())
        self.do(f"task:{core}", "approve")
        self.do(f"task:{core}", "validation_passed", run_id="ci-core")
        # C2 checkpoint: approved files are saved to the project branch right away (F22), by hand here
        self.do("github:save", "prepare_save")
        self.do("github:save", "record", commit_sha="1" * 40)
        self.assertIn("github_save", self.events())
        # milestone 1 done → version 0.1.0 needs a release; both UI tasks are unblocked (wave 2)
        self.do(next(k for k in self.keys() if k.startswith("milestone:")), "accept_milestone")
        self.assertEqual({c.state()["tasks"][t]["status"] for t in (desk, mob)}, {"ready"})
        # F17 → F18 … F21 no (no emergency) → F22 → F23 yes → F24 → F25 yes → F10: the PM wants the next stage
        self.do(next(k for k in self.keys() if k.startswith("github:release:")), "prepare_release")
        self.do(next(k for k in self.keys() if k.startswith("github:release")), "record", tag="v0.1.0",
                commit_sha="1" * 40, run_id="ci-0.1.0")
        self.assertIn("release_published", self.events())
        # the parallel wave: both UI prompts at once (two chats), the third chat stays free
        self.at("F10")
        out = self.do("dispatch", "prepare_all")
        self.assertEqual(len(out["handoff_ids"]), 2)
        self.deliver(desk, ["src/desktop/app.py"])
        # while the mobile AI still works, the desktop delivery is integrated; mobile then finishes too
        self.deliver(mob, ["mobile/MainActivity.kt"])
        self.do("github:save", "prepare_save")
        self.do("github:save", "record", commit_sha="2" * 40)
        # milestone 2 (0.2.0) is complete; its release waits for the manager's decision (F21 no → F22 → F23)
        self.do(next(k for k in self.keys() if k.startswith("milestone:")), "accept_milestone")
        self.events()
        # F17 → F18: every planned task is finished, so the status report is due
        self.edge("F17", "F18", g.find("manager_update")["kind"] == "prompt")
        # the manager defines an emergency: F21 yes → F10 (an urgent fix pauses nothing, it goes first)
        d = self.report([{"operation": "create_task", "temporary_ref": "fix", "title": "Hotfix: data loss on rotate",
                          "objective": "keep todos on rotation", "owner_role": "implementer",
                          "acceptance_criteria": ["no data loss"], "scope": {"include": ["mobile/**"]}}],
                        remaining=True, emergency=[{"ref": "fix", "blocks": []}])
        self.assertEqual(d["route"], "emergency")
        fix = d["emergency"][0]
        self.at("F10")
        self.edge("F21", "F10", "pm_decision" in self.events() and c.state()["tasks"][fix]["priority"] == "critical")
        self.do(f"task:{fix}", "prepare")
        self.deliver(fix, ["mobile/Store.kt"])
        self.events()
        # the next report: no emergency, a stage is left → F21 no → F22 → F23 yes → F24 → F25 yes → F10
        d = self.report([{"operation": "create_task", "temporary_ref": "sync", "title": "Sync", "objective": "sync",
                          "owner_role": "implementer", "acceptance_criteria": ["syncs"], "scope": {"include": ["src/core/sync/**"]}}],
                        remaining=True)
        self.assertEqual(d["route"], "next_stage")
        self.edge("F21", "F22", "github:save" in self.keys())
        self.do("github:save", "prepare_save")
        self.do("github:save", "record", commit_sha="3" * 40)
        self.edge("F22", "F23", "github_save" in self.events())
        rel = next(k for k in self.keys() if k.startswith("github:release:"))
        self.edge("F23", "F24", rel == "github:release:VER-0002")
        self.do(rel, "prepare_release")
        self.do("github:release", "record", tag="v0.2.0", commit_sha="3" * 40, run_id="ci-0.2.0")
        ev = self.events()
        self.edge("F24", "F25", "release_published" in ev)
        self.assertEqual(c.state()["versions"]["VER-0002"]["release"]["run_id"], "ci-0.2.0")
        # F25 yes → F10: stage 3 (sync) is dispatched
        sync = d["created"]["sync"] if "created" in d else max(c.state()["tasks"])
        self.at("F10")
        self.edge("F25", "F10", c.state()["settings"]["flow"]["roadmap_remaining"] is True)
        self.do(f"task:{sync}", "prepare")
        self.deliver(sync, ["src/core/sync/sync.py"])
        self.do("github:save", "prepare_save")
        self.do("github:save", "record", commit_sha="4" * 40)
        self.events()
        # no stage left: F21 no → F22 (already saved) → F23 no (nothing to release) → F25 no → F26
        d = self.report([], remaining=False)
        self.assertEqual(d["route"], "complete")
        self.edge("F23", "F25", not [k for k in self.keys() if k.startswith("github:")])
        self.at("F26")
        self.edge("F25", "F26", self.keys() == ["closeout:announce"])
        self.do("closeout:announce", "announce")
        self.at("F27")
        comp = c.state()["settings"]["flow"]["completion"]
        self.edge("F26", "F27", "project_completed" in self.events() and comp["tasks_done"] == 5)
        self.assertEqual([v["label"] for v in comp["versions_released"]], ["0.1.0", "0.2.0"])
        # F27 yes → F1: expansion opens cycle 2 with the history
        out = self.do("closeout:expand", "expand", idea="Shared lists")
        self.assertIn("Cycle 1 is complete", out["prompt"])
        self.edge("F27", "F1", "project_expanded" in self.events() and c.state()["settings"]["flow"]["cycle"] == 2)
        # cycle 2 is planned and finished quickly, then archived: F27 no → F28
        d = self.report([{"operation": "create_task", "temporary_ref": "share", "title": "Shared lists", "objective": "share",
                          "owner_role": "implementer", "acceptance_criteria": ["shares"], "scope": {"include": ["src/core/share/**"]}}],
                        remaining=False) if self.node() == "F18" else None
        share = max(c.state()["tasks"])
        self.do(f"task:{share}", "prepare")
        self.deliver(share, ["src/core/share/share.py"])
        self.do("github:save", "prepare_save")
        self.do("github:save", "record", commit_sha="5" * 40)
        self.report([], remaining=False)
        self.do("closeout:announce", "announce")
        self.do("closeout:expand", "archive")
        self.at("F28")
        bundle = self.root / ".workbench/archive" / f"{c.state()['project_id']}-final.aiwb-bundle.json"
        self.edge("F27", "F28", bundle.is_file() and "project_archived" in self.events())
        with self.assertRaises(ModelError):
            c.project.tasks.create({"title": "late", "objective": "x"})
        self.assertIsNotNone(d)

        # 100% of the shared contract's edges were observed
        fixture = json.loads(FLOW.read_text(encoding="utf-8"))
        want = {(e["from"], e["to"]) for e in fixture["edges"]}
        self.assertEqual(want, {(a, b) for a, b, _ in flow.EDGES})
        self.assertEqual(sorted(want - self.edges), [], "edges never walked")
        self.assertEqual(len(want), 32)


if __name__ == "__main__":
    unittest.main()
