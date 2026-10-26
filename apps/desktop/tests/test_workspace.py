"""Roadmap 2.3.0: Event Ledger, Account Profiles / Chat Bindings, design tokens, Workspace read models."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2 import V2Project  # noqa: E402
from aiwb.v2.controller import ProjectsController  # noqa: E402
from aiwb.v2.events import EventLedger, to_record  # noqa: E402
from aiwb.v2.models import ModelError  # noqa: E402
from aiwb.v2.resources import binding_readiness  # noqa: E402
from aiwb.v2.store import ProjectStore  # noqa: E402
from aiwb.workspace import theme  # noqa: E402
from aiwb.workspace.controller import SECTIONS, WorkspaceController  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = V2Project(self.root, "ws")
        self.p.open()

    def tearDown(self):
        self.tmp.cleanup()


class LedgerTests(Base):
    def test_every_transaction_event_reaches_the_ledger_once(self):
        t = self.p.tasks.create({"title": "A", "objective": "a"})
        self.p.tasks.transition(t["task_id"], "ready")
        st = self.p.store.load()
        recs = self.p.store.ledger.all()
        self.assertEqual(len(recs), len(st["events"]))
        self.assertEqual([r["state_revision"] for r in recs], [e["state_revision"] for e in st["events"]])
        self.assertEqual(self.p.store.sync_ledger(), 0)  # idempotent
        self.assertEqual(len({r["event_id"] for r in recs}), len(recs))

    def test_redaction_allow_list(self):
        rec = to_record("p", {"type": "handoff_ingested", "at": "2026-10-18T00:00:00Z", "state_revision": 3,
                              "handoff_id": "HO-0001", "prompt": "SECRET PROMPT", "response_text": "x",
                              "token": "ghp_abcdef", "why": "ok ghp_1234567890"}, 0)
        blob = json.dumps(rec)
        self.assertNotIn("SECRET PROMPT", blob)
        self.assertNotIn("ghp_abcdef", blob)
        self.assertIn("[redacted]", blob)
        self.assertEqual(rec["refs"]["handoff_id"], "HO-0001")

    def test_legacy_import_and_unknown_time(self):
        # a 2.2.x project: state with events but no ledger file
        self.p.tasks.create({"title": "A", "objective": "a"})
        self.p.store.ledger.path.unlink()
        st = self.p.store.load()
        st["events"].append({"type": "old_event", "state_revision": st["state_revision"] + 1})
        st["state_revision"] += 1
        self.p.store._write(st)
        V2Project(self.root, "ws").open()
        recs = self.p.store.ledger.all()
        self.assertTrue(all(r.get("legacy_import") for r in recs))
        self.assertEqual(recs[-1]["time_source"], "unknown")
        self.assertEqual(recs[-1]["timestamp_utc"], "")

    def test_torn_line_is_skipped(self):
        self.p.tasks.create({"title": "A", "objective": "a"})
        with open(self.p.store.ledger.path, "a", encoding="utf-8") as fh:
            fh.write('{"schema": "event-ledger.v1", "broken')
        self.assertGreater(self.p.store.ledger.count(), 0)

    def test_query_filter_and_pages(self):
        for i in range(5):
            self.p.tasks.create({"title": f"T{i}", "objective": "o"})
        res = self.p.store.ledger.query(families=["task"], page_size=2)
        self.assertEqual(res["pages"], (res["total"] + 1) // 2)
        self.assertGreaterEqual(res["items"][0]["state_revision"], res["items"][-1]["state_revision"])  # newest first
        one = self.p.store.ledger.query(task_id="TASK-0003")
        self.assertTrue(one["total"] >= 1 and all(r["refs"].get("task_id") == "TASK-0003" for r in one["items"]))

    def test_ledger_failure_never_breaks_state(self):
        store = self.p.store
        orig = store.ledger.append_events
        store.ledger.append_events = lambda *a, **k: (_ for _ in ()).throw(OSError("disk"))
        try:
            self.p.tasks.create({"title": "A", "objective": "a"})
        finally:
            store.ledger.append_events = orig
        self.assertIn("TASK-0001", store.load()["tasks"])
        self.assertGreater(store.sync_ledger(), 0)  # healed on next sync


class ResourceTests(Base):
    def test_account_profile_without_credentials(self):
        acc = self.p.resources.add_account({"display_name": "GPT paid — work", "provider": "GPT", "plan": "paid"})
        self.assertTrue(acc["self_declared"])
        for bad in ({"display_name": "x", "password": "p"}, {"display_name": "sk-abcdefghijklmnop"},
                    {"display_name": "ok", "note": "token: 123"}, {"display_name": "y", "plan": "premium"}):
            with self.assertRaises(ModelError):
                self.p.resources.add_account(bad)
        with self.assertRaises(ModelError):
            self.p.resources.add_account({"display_name": "gpt paid — work"})  # duplicate name

    def test_binding_rules(self):
        acc = self.p.resources.add_account({"display_name": "Gemini free"})
        self.assertEqual(binding_readiness(self.p.store.load(), "agent-implementer")["code"], "no_binding")
        b = self.p.resources.bind_chat("agent-implementer", acc["account_profile_id"], chat_name="impl",
                                       link="https://gemini.google.com/app/abc")
        r = binding_readiness(self.p.store.load(), "agent-implementer")
        self.assertEqual((r["code"], r["binding"]["chat_binding_id"]), ("bound", b["chat_binding_id"]))
        with self.assertRaises(ModelError):
            self.p.resources.update_binding(b["chat_binding_id"], {"agent_id": "agent-reviewer"})
        with self.assertRaises(ModelError):
            self.p.resources.bind_chat("agent-reviewer", acc["account_profile_id"], link="https://x.y/?token=1")
        self.p.resources.set_account_enabled(acc["account_profile_id"], False)
        self.assertEqual(binding_readiness(self.p.store.load(), "agent-implementer")["code"], "account_disabled")
        # agent id and its history are unchanged by binding changes
        self.assertIn("agent-implementer", self.p.store.load()["agents"])

    def test_resources_are_never_published(self):
        from aiwb.v2 import build_snapshot
        self.p.resources.add_account({"display_name": "Private label"})
        snap = json.dumps(build_snapshot(self.p.store.load()))
        self.assertNotIn("Private label", snap)
        self.assertNotIn("account_profiles", snap)

    def test_old_state_without_collections_migrates(self):
        st = self.p.store.load()
        for k in ("account_profiles", "chat_bindings", "milestones", "versions"):
            del st[k]
        self.p.store._write(st)
        notes = ProjectStore(self.root, "ws").ensure_migrated()
        self.assertTrue(any("account_profiles" in n for n in notes))
        self.assertEqual(self.p.store.load()["account_profiles"], {})
        self.assertTrue(list((self.root / ".workbench/v2/backups").glob("*pre-migration*")))


class ThemeTests(unittest.TestCase):
    def test_contrast_and_breakpoints(self):
        self.assertEqual(theme.contrast_problems(), [])
        self.assertEqual(theme.layout_for(1280), {"inspector": "side", "sidebar": "full"})
        self.assertEqual(theme.layout_for(1000), {"inspector": "stacked", "sidebar": "full"})
        self.assertEqual(theme.layout_for(850)["sidebar"], "compact")

    def test_clamp_to_work_area(self):
        self.assertEqual(theme.clamp_to_work_area(1500, 900, 1280, 760, (0, 0, 1366, 720)), (86, 0, 1280, 720))
        self.assertEqual(theme.clamp_to_work_area(-50, -50, 2000, 2000, (0, 0, 1280, 672)), (0, 0, 1280, 672))


class WorkspaceControllerTests(Base):
    def setUp(self):
        super().setUp()
        self.ctl = ProjectsController(self.root)
        self.wc = WorkspaceController(self.ctl)

    def test_view_preferences_never_touch_project_state(self):
        rev, n = self.ctl.project.store.revision, self.ctl.project.store.ledger.count()
        for s in SECTIONS:
            self.wc.set_section(s)
        self.wc.set_inspector(False)
        self.wc.set_sidebar(False)
        self.wc.set_theme("dark")
        self.wc.set_language("fa")
        self.wc.set_mode("advanced")
        self.wc.timeline_page(0, families=["task"])
        self.wc.overview()
        self.assertEqual((self.ctl.project.store.revision, self.ctl.project.store.ledger.count()), (rev, n))
        again = WorkspaceController(ProjectsController(self.root))
        self.assertEqual((again.section, again.inspector_open, again.sidebar_open, again.theme), ("project", False, False, "dark"))

    def test_old_section_keys_are_aliases(self):
        """5.11.0: seven sections became three; 5.13.0: Timeline moved to the Mission Map — the old keys still work."""
        from aiwb.workspace.controller import canonical_section
        self.assertEqual(SECTIONS, ("plan", "project"))
        for old, new in (("overview", "plan"), ("tasks", "plan"), ("team", "project"), ("files", "project"),
                         ("versions", "project"), ("settings", "project"), ("timeline", "plan")):
            self.assertEqual(canonical_section(old), new)
            self.wc.set_section(old)
            self.assertEqual(self.wc.section, new)
        with self.assertRaises(ModelError):
            self.wc.set_section("nope")
        self.ctl._save_ui(ws_section="nope")
        self.assertEqual(WorkspaceController(ProjectsController(self.root)).section, "plan")

    def test_overview_progress_is_count_based_and_explained(self):
        p = self.ctl.project
        a = p.tasks.create({"title": "A", "objective": "a"})
        p.tasks.create({"title": "B", "objective": "b"})
        c = p.tasks.create({"title": "C", "objective": "c"})
        p.tasks.transition(c["task_id"], "cancelled")
        ov = self.wc.overview()
        self.assertEqual({k: ov["progress"][k] for k in ("done", "total", "percent")}, {"done": 0, "total": 2, "percent": 0})
        self.assertIn("by count", self.wc.progress_text({"done": 1, "total": 2, "percent": 50}))
        self.wc.set_language("fa")
        self.assertIn("از", self.wc.progress_text({"done": 1, "total": 2, "percent": 50}))
        self.wc.select("task", a["task_id"])
        insp = self.wc.inspector()
        self.assertIn(a["task_id"], insp["title"])

    def test_team_rows_and_inspector_actions(self):
        acc = self.wc.add_account({"display_name": "Claude team", "plan": "team"})
        self.wc.bind_chat("agent-reviewer", acc["account_profile_id"], "review chat")
        rows = {r["agent_id"]: r for r in self.wc.team_rows()}
        self.assertEqual(rows["agent-reviewer"]["account"], "Claude team")
        self.assertEqual(rows["agent-implementer"]["readiness"], "no_binding")
        self.wc.select("agent", "agent-reviewer")
        self.assertEqual(self.wc.inspector()["actions"][0][0], "bind_chat")
        t = self.ctl.project.tasks.create({"title": "A", "objective": "a", "owner_agent_id": "agent-implementer"})
        self.ctl.project.tasks.transition(t["task_id"], "ready")
        self.wc.select("task", t["task_id"])
        self.assertIn("start_task", [k for k, _ in self.wc.inspector()["actions"]])
        h = self.wc.run_action("start_task")
        self.assertTrue(h["prompt"].startswith("AIWB_ATTEMPT_ID"))
        ev = self.wc.timeline_page(0, task_id=t["task_id"])["items"][0]
        self.wc.select("event", ev["event_id"])
        self.assertEqual(self.wc.run_action("open_task"), ("task", t["task_id"]))

    def test_tools_only_when_wired(self):
        calls = []
        wc = WorkspaceController(self.ctl, tools={"inbox": lambda: calls.append("inbox")})
        self.assertEqual([k for k, _ in wc.tool_items("files")], ["inbox"])
        wc.open_tool("inbox")
        self.assertEqual(calls, ["inbox"])
        with self.assertRaises(ModelError):
            wc.open_tool("companion")


if __name__ == "__main__":
    unittest.main()
