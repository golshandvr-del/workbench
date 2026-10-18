"""Roadmap 1.17.0/1.17.1 (slices 2A, 2B): data model, migration, state machines, agents, task graph."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2 import ModelError, StoreError, V2Project, validate_graph  # noqa: E402
from aiwb.v2.models import MACHINES, check_transition  # noqa: E402
from aiwb.v2.store import DB_VERSION, migrate_state  # noqa: E402
from aiwb.v2.tasks import find_cycle, scopes_overlap  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = V2Project(self.root, "demo")
        self.p.open()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def task(self, title="T", **kw):
        return self.p.tasks.create({"title": title, "objective": "do " + title, **kw})


class StoreAndMigrationTests(Base):
    def test_fresh_store_has_base_agents_and_revision(self):
        self.assertEqual(sorted(a["agent_id"] for a in self.p.agents.list()),
                         ["agent-architect", "agent-implementer", "agent-project-manager", "agent-reviewer"])
        self.assertGreater(self.p.store.revision, 0)
        self.assertEqual(self.p.store.load()["db_version"], DB_VERSION)

    def test_migration_is_idempotent_and_backs_up(self):
        before = self.p.store.revision
        self.assertEqual(self.p.open(), [])
        self.assertEqual(self.p.store.revision, before)
        raw = json.loads(self.p.store.path.read_text())
        del raw["decisions"]
        raw["db_version"] = 0
        raw["custom_future_field"] = {"keep": True}
        raw["tasks"]["TASK-0099"] = {"task_id": "TASK-0099", "title": "old", "status": "done", "odd": 1}
        self.p.store.path.write_text(json.dumps(raw))
        notes = self.p.open()
        self.assertIn("migrated to db_version 1", notes)
        st = self.p.store.load()
        self.assertEqual(st["custom_future_field"], {"keep": True})
        self.assertEqual(st["tasks"]["TASK-0099"]["odd"], 1, "historic fields must survive")
        self.assertEqual(st["decisions"], {})
        self.assertTrue(list((self.p.store.dir / "backups").glob("*pre-migration*.json")))
        self.assertEqual(self.p.open(), [], "second run is a no-op")

    def test_newer_db_and_corrupt_file_are_refused_without_writing(self):
        raw = json.loads(self.p.store.path.read_text())
        raw["db_version"] = DB_VERSION + 1
        self.p.store.path.write_text(json.dumps(raw))
        with self.assertRaises(StoreError):
            self.p.store.load()
        self.p.store.path.write_text("{broken")
        with self.assertRaises(StoreError):
            self.p.tasks.create({"title": "x", "objective": "y"})
        self.assertEqual(self.p.store.path.read_text(), "{broken")

    def test_malformed_collection_is_quarantined_not_lost(self):
        state, notes = migrate_state({"db_version": 1, "tasks": ["weird"]}, "p")
        self.assertEqual(state["tasks"], {})
        self.assertEqual(state["_quarantine"]["tasks"], ["weird"])

    def test_failed_transaction_leaves_file_untouched(self):
        text = self.p.store.path.read_text()
        with self.assertRaises(RuntimeError):
            with self.p.store.transaction("boom") as s:
                s["tasks"]["TASK-9999"] = {}
                raise RuntimeError("x")
        self.assertEqual(self.p.store.path.read_text(), text)

    def test_concurrent_transactions_lose_nothing(self):
        def work(i):
            self.task(f"t{i}")
        threads = [threading.Thread(target=work, args=(i,)) for i in range(12)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        ids = [t["task_id"] for t in self.p.tasks.list()]
        self.assertEqual(len(ids), 12)
        self.assertEqual(len(set(ids)), 12)

    def test_legacy_task_and_attempts_linked_once(self):
        root = self.root / "legacy"
        root.mkdir()
        p = V2Project(root)
        legacy = {"task_state": {"task_id": "task-20260101-x", "task_text": "Old task\nmore"},
                  "attempts": [{"attempt_id": "att-20260101-000000-deadbeef", "task_id": "task-20260101-x", "status": "answered"},
                               {"attempt_id": "att-20260101-000001-deadbeef", "task_id": "other", "status": "sent"}]}
        notes = p.open(legacy)
        self.assertTrue(any("legacy task" in n for n in notes))
        st = p.store.load()
        (tid, t), = st["tasks"].items()
        self.assertEqual((t["title"], t["origin"], t["legacy_task_id"]), ("Old task", "migration", "task-20260101-x"))
        a1 = st["attempts"]["att-20260101-000000-deadbeef"]
        self.assertEqual((a1["task_id"], a1["status"], a1["legacy"]), (tid, "response_received", True))
        self.assertEqual(st["attempts"]["att-20260101-000001-deadbeef"]["task_id"], "", "unrelated attempt stays legacy-only")
        self.assertEqual(p.open(legacy), [])


class StateMachineTests(unittest.TestCase):
    def test_every_target_exists_and_illegal_moves_fail(self):
        for kind, m in MACHINES.items():
            for src, targets in m.items():
                self.assertTrue(targets <= set(m), (kind, src))
        with self.assertRaises(ModelError):
            check_transition("task", "cancelled", "ready")
        with self.assertRaises(ModelError):
            check_transition("attempt", "accepted", "parsed")
        with self.assertRaises(ModelError):
            check_transition("task", "draft", "nope")
        check_transition("task", "draft", "ready")


class AgentTests(Base):
    def test_templates_never_overwrite_user_edits(self):
        self.p.agents.update("agent-implementer", {"preferred_model_label": "Gemini", "instructions": ["mine"]})
        self.assertEqual(self.p.agents.install_templates(), [])
        a = self.p.agents.get("agent-implementer")
        self.assertEqual((a["instructions"], a["revision"], a["preferred_model_label"]), (["mine"], 2, "Gemini"))

    def test_id_stable_copy_disable_validation(self):
        with self.assertRaises(ModelError):
            self.p.agents.update("agent-reviewer", {"agent_id": "agent-x"})
        c = self.p.agents.copy("agent-reviewer", "agent-security-reviewer", "Security reviewer")
        self.assertEqual((c["role"], c["revision"]), ("reviewer", 1))
        self.p.agents.set_enabled("agent-security-reviewer", False)
        self.assertNotIn("agent-security-reviewer", [a["agent_id"] for a in self.p.agents.list(include_disabled=False)])
        for bad in ({"agent_id": "Bad Id", "name": "x", "role": "implementer"},
                    {"agent_id": "agent-y", "name": "x", "role": "wizard"},
                    {"agent_id": "agent-implementer", "name": "dup", "role": "implementer"}):
            with self.assertRaises(ModelError):
                self.p.agents.create(bad)


class TaskGraphTests(Base):
    def test_graph_validation(self):
        self.assertEqual(find_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}), ["a", "b", "c", "a"])
        self.assertIsNone(find_cycle({"a": ["b"], "b": []}))
        probs = validate_graph({"A": {"depends_on": ["A", "Z"]}})
        self.assertTrue(any("itself" in p for p in probs) and any("unknown" in p for p in probs))
        a = self.task("A")
        with self.assertRaises(ModelError):
            self.task("B", depends_on=["TASK-9999"])
        b = self.task("B", depends_on=[a["task_id"]])
        with self.assertRaises(ModelError):
            self.p.tasks.update(a["task_id"], {"depends_on": [b["task_id"]]})
        self.assertEqual(self.p.tasks.get(a["task_id"])["depends_on"], [], "rejected graph is not saved")

    def test_ready_only_when_prereqs_done_and_cancel_blocks(self):
        a = self.task("A")
        b = self.task("B", depends_on=[a["task_id"]])
        with self.assertRaises(ModelError):
            self.p.tasks.transition(b["task_id"], "ready")
        self.p.tasks.transition(b["task_id"], "blocked", "waiting for " + a["task_id"])
        with self.assertRaises(ModelError):
            self.p.tasks.transition(a["task_id"], "done")
        self.p.tasks.transition(a["task_id"], "cancelled", "dropped")
        b2 = self.p.tasks.get(b["task_id"])
        self.assertEqual(b2["status"], "blocked")
        self.assertIn("re-plan", b2["blocked_reason"])

    def test_revision_on_contract_change_flags_dependants(self):
        a = self.task("A", acceptance_criteria=["c1"])
        b = self.task("B", depends_on=[a["task_id"]])
        same = self.p.tasks.update(a["task_id"], {"priority": "high"})
        self.assertEqual(same["task_revision"], 1)
        up = self.p.tasks.update(a["task_id"], {"acceptance_criteria": ["c1", "c2"]}, reason="stricter")
        self.assertEqual(up["task_revision"], 2)
        self.assertEqual(up["revisions"][0]["fields"]["acceptance_criteria"], ["c1"])
        self.assertTrue(self.p.tasks.get(b["task_id"])["flags"])
        with self.assertRaises(ModelError):
            self.p.tasks.update(a["task_id"], {"status": "done"})

    def test_reassign_keeps_task_id_and_owner_must_exist(self):
        t = self.task("A", owner_agent_id="agent-implementer")
        t2 = self.p.tasks.update(t["task_id"], {"owner_agent_id": "agent-architect"})
        self.assertEqual(t2["task_id"], t["task_id"])
        with self.assertRaises(ModelError):
            self.task("B", owner_agent_id="agent-ghost")

    def test_parallel_candidates_respect_scope(self):
        a = self.task("A", scope={"include": ["apps/desktop/**"]})
        b = self.task("B", scope={"include": ["apps/mobile/**"]})
        c = self.task("C", scope={"include": ["apps/desktop/src/x.py"]})
        for t in (a, b, c):
            self.p.tasks.transition(t["task_id"], "ready")
        pairs = self.p.tasks.parallel_candidates()
        self.assertIn((a["task_id"], b["task_id"]), pairs)
        self.assertNotIn((a["task_id"], c["task_id"]), pairs)
        self.assertTrue(scopes_overlap({"include": []}, {"include": ["x"]}), "unknown scope counts as overlap")


if __name__ == "__main__":
    unittest.main()
