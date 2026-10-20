"""Roadmap 4.5.0 gate: GitHub blue nodes of the owner's algorithm (flowchart F3, F22–F24).

* every write is prepare → confirm with the action id; nothing is sent before confirm, a stale id sends nothing;
* F3 connect/create binds the repo and a project branch (never main); F22 saves integrated files in one
  fast-forward commit; F23/F24 a version with all milestones accepted is tagged and released;
* without a token every step is manual instructions + "record" (never a dead end);
* the shared fixture ``packages/contracts/fixtures/repo/github-flow.v1.json`` (branch names, refusals) passes.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aiwb.v2 import ModelError, V2Project  # noqa: E402
from aiwb.v2 import repo as repo_mod  # noqa: E402
from aiwb.v2.publisher import ApiResult, GitHubStateClient  # noqa: E402
from aiwb.v2.repo import RepoService, project_branch, release_needed, unsaved_files  # noqa: E402
from test_v2_flow import FakeGitHub  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[3] / "packages/contracts/fixtures/repo/github-flow.v1.json"


class FakeHub(FakeGitHub):
    """FakeGitHub + the absolute endpoints used by repo.py (create repo, get repo, releases)."""

    def __init__(self):
        super().__init__()
        self.releases, self.created = [], []

    def __call__(self, method, url, headers, body):
        if url.endswith("/user/repos") and method == "POST":
            self.calls.append((method, "/user/repos"))
            self.created.append(json.loads(body)["name"])
            return ApiResult(201, {"html_url": "https://github.com/o/r", "default_branch": "main"}, {})
        if url.endswith("/releases") and method == "POST":
            self.calls.append((method, "/releases"))
            self.releases.append(json.loads(body))
            return ApiResult(201, {"html_url": "https://github.com/o/r/releases/tag/x"}, {})
        if method == "GET" and url.endswith("/repos/o/r"):
            self.calls.append((method, ""))
            return ApiResult(200, {"default_branch": self.default, "html_url": "https://github.com/o/r"}, {})
        return super().__call__(method, url, headers, body)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = V2Project(self.root, "demo")
        self.p.open()
        self.gh = FakeHub()
        self.svc = RepoService(self.p.store, self.root,
                               client_factory=lambda o, n: GitHubStateClient("tok", o, n, transport=self.gh))

    def tearDown(self):
        self.tmp.cleanup()

    def integrated(self, hid="H-1", files=("src/a.py",)):
        for f in files:
            (self.root / f).parent.mkdir(parents=True, exist_ok=True)
            (self.root / f).write_text(f"# {f}\n", encoding="utf-8")
        with self.p.store.transaction("fake integrate") as s:
            s["handoffs"][hid] = {"handoff_id": hid, "integrated_files": list(files), "integrated_at": "2026-01-01T00:00:00Z"}

    def connect(self):
        a = self.svc.prepare("connect", owner="o", name="r")
        self.svc.confirm(a["action_id"])

    def ready_version(self):
        t = self.p.tasks.create({"title": "A", "objective": "a", "owner_agent_id": "agent-implementer",
                                 "acceptance_criteria": ["ok"]})
        m = self.p.timeline.create_milestone({"title": "M", "task_ids": [t["task_id"]]})
        v = self.p.timeline.propose_version({"label": "1.0.0", "milestone_ids": [m["milestone_id"]]})
        self.p.timeline.accept_milestone(m["milestone_id"], force=True)
        return v


class HandshakeTests(Base):
    def test_prepare_sends_nothing_and_confirm_needs_the_id(self):
        a = self.svc.prepare("connect", owner="o", name="r")
        self.assertEqual(self.gh.calls, [], "prepare never calls GitHub")
        with self.assertRaises(ModelError):
            self.svc.confirm("gh-wrong")
        self.assertEqual(self.gh.calls, [])
        self.svc.confirm(a["action_id"])
        with self.assertRaises(ModelError):
            self.svc.confirm(a["action_id"])  # already done: nothing sent twice
        info = repo_mod.repo_info(self.p.store.load())
        self.assertEqual((info["full_name"], info["branch"]), ("o/r", "aiwb/demo"))
        self.assertEqual(self.gh.refs["aiwb/demo"], "c0", "project branch created from the default head")
        self.assertEqual(self.gh.refs["main"], "c0", "main untouched")

    def test_cancel(self):
        self.svc.prepare("connect", owner="o", name="r")
        self.svc.cancel()
        self.assertIsNone(self.svc.pending())

    def test_create_is_private(self):
        a = self.svc.prepare("create", owner="o", name="r")
        self.svc.confirm(a["action_id"])
        self.assertEqual(self.gh.created, ["r"])

    def test_refusals(self):
        with self.assertRaises(ModelError):
            self.svc.prepare("connect", owner="o", name="r", branch="main")
        with self.assertRaises(ModelError):
            self.svc.prepare("save")  # not connected
        self.connect()
        with self.assertRaises(ModelError):
            self.svc.prepare("save")  # nothing integrated
        with self.assertRaises(ModelError):
            self.svc.prepare("release")  # no version ready


class SaveReleaseTests(Base):
    def test_save_then_release(self):
        self.connect()
        self.integrated()
        self.assertEqual(unsaved_files(self.p.store.load()), ["src/a.py"])
        a = self.svc.prepare("save")
        out = self.svc.confirm(a["action_id"])
        self.assertEqual(self.gh.files("aiwb/demo"), {"src/a.py": "# src/a.py\n"})
        self.assertEqual(self.gh.refs["main"], "c0")
        self.assertEqual(unsaved_files(self.p.store.load()), [])
        self.assertEqual(repo_mod.repo_info(self.p.store.load())["head"], out["commit_sha"])

        v = self.ready_version()
        self.assertEqual([x["version_id"] for x in release_needed(self.p.store.load())], [v["version_id"]])
        a = self.svc.prepare("release", version_id=v["version_id"])
        self.assertEqual(a["payload"]["tag"], "v1.0.0")
        self.svc.confirm(a["action_id"])
        st = self.p.store.load()
        rv = st["versions"][v["version_id"]]
        self.assertEqual((rv["status"], rv["tag"]), ("released", "v1.0.0"))
        self.assertEqual(self.gh.refs["v1.0.0"], out["commit_sha"], "tag on the saved commit")
        self.assertEqual(self.gh.releases[0]["tag_name"], "v1.0.0")
        self.assertEqual(release_needed(st), [])


class ManualModeTests(Base):
    def setUp(self):
        super().setUp()
        self.svc.client_factory = None

    def test_manual_record(self):
        a = self.svc.prepare("connect", owner="o", name="r")
        self.assertTrue(a["manual"])
        self.assertTrue(a["steps"])
        with self.assertRaises(ModelError):
            self.svc.confirm(a["action_id"])
        self.svc.record("connect")
        self.integrated()
        self.svc.prepare("save")
        with self.assertRaises(ModelError):
            self.svc.record("save")  # SHA required
        self.svc.record("save", commit_sha="abc123")
        self.assertEqual(unsaved_files(self.p.store.load()), [])
        self.assertEqual(self.gh.calls, [], "manual mode never calls GitHub")


class GuideTests(Base):
    def test_guide_steps(self):
        from aiwb.v2.controller import ProjectsController
        from aiwb.v2.guide import Guide
        ctl = ProjectsController(self.root)
        ctl.repo.client_factory = self.svc.client_factory
        g = Guide(ctl)
        from aiwb.v2.flow import start_project
        start_project(ctl.project.store, {"goal": "Build a calculator"})
        keys = [s["key"] for s in g.steps()]
        self.assertIn("github:connect", keys)
        self.assertIn("manager_update", keys, "optional GitHub step never hides the manager update")
        g.perform("github:connect", "prepare_connect", owner="o", name="r")
        step = next(s for s in g.steps() if s["key"] == "github:connect")
        self.assertEqual(step["kind"], "decision")
        self.assertIn("confirm", [x["id"] for x in step["actions"]])
        g.perform("github:connect", "confirm")
        self.assertEqual(repo_mod.repo_info(ctl.state())["full_name"], "o/r")


class FixtureTests(unittest.TestCase):
    def test_fixture(self):
        fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for c in fx["project_branch"]:
            with self.subTest(c=c):
                self.assertEqual(project_branch({"settings": {"brief": {"name": c["name"]}}, "project_id": "p"}), c["out"])
        for name in fx["refused_branches"]:
            with self.subTest(name=name):
                self.assertIn(name, repo_mod.PROTECTED_BRANCHES)
        for c in fx["names"]:
            with self.subTest(c=c):
                self.assertEqual(bool(repo_mod._NAME.match(c["in"])), c["ok"])


if __name__ == "__main__":
    unittest.main()
