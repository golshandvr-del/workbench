"""Roadmap 3.9.0 — product Release Gate (end-to-end, desktop side).

One scripted run over the public services only:

1. idea → charter prompt → a *dirty* chat copy of the Project Charter (smart quotes, NBSP, escaped
   markers, an outer fence — what ChatGPT really produces) is normalised and imported;
2. the guided loop alone drives three AIs from the charter to two released versions (no dead end in
   any reached state; model claims never count as validation);
3. the project is exported as ``aiwb-bundle.v1``, imported into an empty project (the phone side of the
   round trip), re-exported byte-identically, and the mobile-produced fixture is accepted as *newer*;
4. performance budgets: opening the finished project, computing the guide steps and exporting the
   bundle stay well below interactive limits on CI hardware.

Physical Windows, a real phone and real chat models are NOT RUN here (see RELEASE_GATE_v3.9.0.md).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import AI_Workbench as wb  # noqa: E402
from aiwb.v2 import bundle  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.guide import KINDS, Guide  # noqa: E402
from test_v2_guide import answer_for  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
CHARTER = REPO / "packages/contracts/fixtures/valid/project-charter.v1.todo.json"
MOBILE = REPO / "packages/contracts/fixtures/bundle/todo.mobile.aiwb-bundle.json"

# Budgets (milliseconds) — generous for shared CI runners; the measured numbers are in the gate report.
BUDGET_OPEN_MS = 1500
BUDGET_STEPS_MS = 500
BUDGET_EXPORT_MS = 500


def dirty_charter(data: dict) -> str:
    body = json.dumps(data, indent=2).replace('"summary"', '\u00a0"summary"', 1)
    return ("Sure! Here\u2019s the charter you asked for:\n\n```\n"
            "\\<\\<\\<AIWB\\_PROJECT\\_CHARTER>>>\n" + body + "\n<<<AIWB\\_END\\_PROJECT\\_CHARTER>>>\n```\n"
            "Let me know if you want changes.\n")


def ms(t0: float) -> float:
    return (time.perf_counter() - t0) * 1000


@unittest.skipUnless(CHARTER.exists(), "shared contracts are only present in the repository checkout")
class ReleaseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def project(self, name: str) -> ProjectsController:
        root = self.base / name
        root.mkdir(parents=True)
        return ProjectsController(root, make_pipeline=wb.make_inbox_pipeline)

    def assert_no_dead_end(self, g: Guide) -> list[dict]:
        steps = g.steps()
        self.assertTrue(steps, "dead end: no step")
        for s in steps:
            self.assertIn(s["kind"], KINDS)
            self.assertTrue(s["actions"], s["key"])
        return steps

    def run_loop(self, c: ProjectsController, g: Guide) -> int:
        scope = {t["task_id"]: t["scope"]["include"] for t in c.state()["tasks"].values()}
        n = 0
        for n in range(1, 300):
            if all(v["status"] == "released" for v in c.state()["versions"].values()):
                return n
            steps = self.assert_no_dead_end(g)
            step = next((s for s in steps if s["key"].startswith("task:") and s["actions"][0]["id"] == "prepare"), steps[0])
            key, first = step["key"], next(a["id"] for a in step["actions"] if a["primary"])
            if key.startswith("handoff:") and step["kind"] in ("prompt", "paste"):
                if first in ("copy", "sent"):
                    g.perform(key, first)
                else:
                    h = dict(c.project.handoffs.get(step["ref"]))
                    h["_scope"] = scope[h["task_id"]]
                    r = g.perform(key, "paste", text=answer_for(h))
                    self.assertEqual(r["kind"], "handoff", r["message"])
            elif key.startswith("task:") and first == "prepare":
                g.perform(key, "prepare")
            elif key.startswith("handoff:"):
                g.perform(key, "accept_handoff")
            elif key.startswith("task:") and first == "approve":
                g.perform(key, "approve")
            elif key.startswith("task:") and first == "record_validation":
                # the AI claimed "tests pass"; only the recorded run counts
                g.perform(key, "record_validation", result="passed", run_id="run-" + step["ref"])
            elif key.startswith("milestone:"):
                g.perform(key, "accept_milestone")
            elif key.startswith("version:"):
                g.perform(key, "release", commit_sha="b" * 40, tag="", run_id="run-rel-" + step["ref"])
            else:
                self.fail(f"scripted user does not know step {key} / {first}")
        self.fail("loop did not reach released versions")

    def test_full_product_flow_desktop_to_phone_bundle(self) -> None:
        c = self.project("desk/todo")
        g = Guide(c)
        g.perform("design", "design", goal="An offline todo app for desktop and mobile")
        g.perform("charter", "copy")
        g.perform("charter", "sent")
        data = json.loads(CHARTER.read_text(encoding="utf-8"))
        data["base_state_revision"] = c.state()["state_revision"]
        out = g.perform("charter", "paste", text=dirty_charter(data))
        self.assertEqual(out["kind"], "proposal", out["message"])
        g.perform(self.assert_no_dead_end(g)[0]["key"], "accept")
        st = c.state()
        self.assertEqual((len(st["tasks"]), len(st["versions"])), (3, 2))

        rounds = self.run_loop(c, g)
        st = c.state()
        self.assertTrue(all(t["status"] == "done" for t in st["tasks"].values()))
        self.assertTrue(all(m["status"] == "accepted" for m in st["milestones"].values()))
        self.assertEqual(self.assert_no_dead_end(g)[-1]["key"], "manager_update")
        self.assertLess(rounds, 300)

        # desktop → phone → desktop
        text = c.export_bundle()
        phone = self.project("phone/todo")
        self.assertEqual(phone.plan_bundle_import(text)["kind"], "new")
        self.assertTrue(phone.import_bundle(text)["imported"])
        self.assertEqual(phone.plan_bundle_import(text)["kind"], "same")
        self.assertEqual(c.plan_bundle_import(phone.export_bundle())["kind"], "same")
        _, back = bundle.read_bundle(phone.export_bundle())
        self.assertEqual(back["versions"], st["versions"])

    @unittest.skipUnless(MOBILE.exists(), "mobile bundle fixture missing")
    def test_mobile_produced_bundle_is_accepted(self) -> None:
        b, st = bundle.read_bundle(MOBILE.read_bytes())
        self.assertEqual(b["producer"]["app"], bundle.MOBILE_APP)
        c = self.project("from-phone/todo")
        self.assertTrue(c.import_bundle(MOBILE.read_bytes())["imported"])
        self.assertTrue(Guide(c).steps(), "imported phone project has a next step")

    def test_performance_budgets(self) -> None:
        c = self.project("perf/todo")
        g = Guide(c)
        g.perform("design", "design", goal="perf")
        data = json.loads(CHARTER.read_text(encoding="utf-8"))
        data["base_state_revision"] = c.state()["state_revision"]
        g.perform("charter", "paste", text=dirty_charter(data))
        g.perform(g.steps()[0]["key"], "accept")
        self.run_loop(c, g)
        root = c.project.root if hasattr(c.project, "root") else self.base / "perf/todo"
        t0 = time.perf_counter()
        c2 = ProjectsController(root, make_pipeline=wb.make_inbox_pipeline)
        open_ms = ms(t0)
        t0 = time.perf_counter()
        Guide(c2).steps()
        steps_ms = ms(t0)
        t0 = time.perf_counter()
        c2.export_bundle()
        export_ms = ms(t0)
        print(f"\n[release-gate] open={open_ms:.1f}ms steps={steps_ms:.1f}ms export={export_ms:.1f}ms", file=sys.stderr)
        self.assertLess(open_ms, BUDGET_OPEN_MS)
        self.assertLess(steps_ms, BUDGET_STEPS_MS)
        self.assertLess(export_ms, BUDGET_EXPORT_MS)


if __name__ == "__main__":
    unittest.main()
