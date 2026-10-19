"""Roadmap 3.8.0 Gate (desktop side): aiwb-bundle.v1 export / import round trip and safety rules.

The shared fixture ``packages/contracts/fixtures/bundle/todo.aiwb-bundle.json`` is a bundle produced by this
desktop code from the Project Charter fixture; the Android tests (BundleContractTest) read the same file and
must produce a bundle this module accepts.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aiwb.v2 import bundle  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
CHARTER = REPO / "packages" / "contracts" / "fixtures" / "valid" / "project-charter.v1.todo.json"
SHARED = REPO / "packages" / "contracts" / "fixtures" / "bundle" / "todo.aiwb-bundle.json"


def charter_project(root: Path) -> ProjectsController:
    ctl = ProjectsController(root)
    text = CHARTER.read_text(encoding="utf-8").replace('"base_state_revision": 3', '"base_state_revision": 0')
    ctl.import_charter("<<<AIWB_PROJECT_CHARTER>>>\n" + text + "\n<<<AIWB_END_PROJECT_CHARTER>>>")
    st = ctl.state()
    pid = next(iter(st["proposals"]))
    ctl.accept_proposal(pid, list(range(len(st["proposals"][pid]["operations"]))))
    return ctl


@unittest.skipUnless(CHARTER.exists(), "shared contracts are only present in the repository checkout")
class BundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def folder(self, name: str) -> Path:
        p = self.base / name
        p.mkdir()
        return p

    def test_export_shape_and_integrity(self) -> None:
        ctl = charter_project(self.folder("todo"))
        b = json.loads(ctl.export_bundle(version="3.8.0"))
        self.assertEqual((b["bundle_type"], b["bundle_version"]), ("aiwb-bundle", 1))
        self.assertEqual(b["producer"], {"app": "ai-workbench-desktop", "version": "3.8.0"})
        self.assertEqual(b["state_sha256"], bundle.sha256_hex(b["state_json"]))
        st = json.loads(b["state_json"])
        self.assertEqual(st["project_id"], "todo")
        self.assertEqual(len(st["tasks"]), 3)
        self.assertIn("charter", st["settings"])

    def test_round_trip_into_empty_project_is_identical(self) -> None:
        src = charter_project(self.folder("todo"))
        text = src.export_bundle()
        dst_root = self.base / "copy" / "todo"
        dst_root.mkdir(parents=True)
        dst = ProjectsController(dst_root)
        self.assertEqual(dst.plan_bundle_import(text)["kind"], "new")
        out = dst.import_bundle(text)
        self.assertTrue(out["imported"])
        a, b = src.state(), dst.state()
        b["settings"].pop("sync")
        self.assertEqual(a, b)
        self.assertEqual(dst.plan_bundle_import(text)["kind"], "same")

    def test_newer_bundle_replaces_with_backup(self) -> None:
        a = charter_project(self.folder("todo"))
        b_root = self.base / "b" / "todo"
        b_root.mkdir(parents=True)
        b = ProjectsController(b_root)
        b.import_bundle(a.export_bundle())
        a.start_task("TASK-0001")                  # work continues on A (e.g. on the phone)
        plan = b.plan_bundle_import(a.export_bundle())
        self.assertEqual(plan["kind"], "newer")
        self.assertTrue(plan["safe"])
        b.import_bundle(a.export_bundle())
        self.assertEqual(b.state()["tasks"]["TASK-0001"]["status"], "in_progress")
        self.assertTrue(list((b_root / ".workbench" / "v2" / "backups").glob("*pre-bundle-import*")))

    def test_older_and_diverged_are_refused_without_force(self) -> None:
        a = charter_project(self.folder("todo"))
        old = a.export_bundle()
        b_root = self.base / "b" / "todo"
        b_root.mkdir(parents=True)
        b = ProjectsController(b_root)
        b.import_bundle(old)
        a.start_task("TASK-0001")
        self.assertEqual(a.plan_bundle_import(old)["kind"], "older")
        with self.assertRaises(bundle.BundleError):
            a.import_bundle(old)
        b.set_team_settings(max_parallel_chats=3)  # B changes too → diverged
        plan = b.plan_bundle_import(a.export_bundle())
        self.assertEqual(plan["kind"], "diverged")
        with self.assertRaises(bundle.BundleError):
            b.import_bundle(a.export_bundle())
        self.assertTrue(b.import_bundle(a.export_bundle(), force=True)["imported"])

    def test_other_project_and_damage_rejected(self) -> None:
        a = charter_project(self.folder("todo"))
        other = charter_project(self.folder("other"))
        with self.assertRaises(bundle.BundleError):
            a.import_bundle(other.export_bundle(), force=True)
        good = json.loads(a.export_bundle())
        bad = dict(good, state_json=good["state_json"].replace("Core library", "Core librarx"))
        with self.assertRaisesRegex(bundle.BundleError, "damaged"):
            bundle.read_bundle(json.dumps(bad))
        for broken, why in (({**good, "bundle_type": "x"}, "bundle_type"), ({**good, "bundle_version": 2}, "bundle_version"),
                            ("not json", "not valid JSON")):
            with self.assertRaisesRegex(bundle.BundleError, why):
                bundle.read_bundle(broken if isinstance(broken, str) else json.dumps(broken))

    def test_newer_db_version_refused(self) -> None:
        a = charter_project(self.folder("todo"))
        st = a.state()
        st["db_version"] = 99
        with self.assertRaisesRegex(bundle.BundleError, "newer"):
            bundle.read_bundle(bundle.export_bundle(st))

    @unittest.skipUnless(SHARED.exists(), "shared bundle fixture missing")
    def test_shared_fixture_imports(self) -> None:
        b, st = bundle.read_bundle(SHARED.read_bytes())
        self.assertEqual(st["project_id"], "todo")
        self.assertEqual(sorted(st["tasks"]), ["TASK-0001", "TASK-0002", "TASK-0003"])
        root = self.base / "shared" / "todo"
        root.mkdir(parents=True)
        self.assertTrue(ProjectsController(root).import_bundle(SHARED.read_bytes())["imported"])


if __name__ == "__main__":
    unittest.main()
