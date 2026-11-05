"""Roadmap 5.16.0 (R2): the V2 state cache is fast, returns independent copies and never serves stale data."""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2 import store as S  # noqa: E402
from aiwb.v2.store import ProjectStore, emit  # noqa: E402


class StoreCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()
        self.store = ProjectStore(self.root)
        with self.store.transaction("seed") as s:
            s["settings"]["goal"] = "calc"
            emit(s, "seeded")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_load_returns_independent_copies(self) -> None:
        a = self.store.load()
        a["settings"]["goal"] = "changed in memory"
        a["tasks"]["X"] = {}
        b = self.store.load()
        self.assertEqual(b["settings"]["goal"], "calc")
        self.assertNotIn("X", b["tasks"])

    def test_external_write_is_seen(self) -> None:
        self.store.load()
        data = json.loads(self.store.path.read_text(encoding="utf-8"))
        data["settings"]["goal"] = "edited by another process, longer text"
        self.store.path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.store.load()["settings"]["goal"], "edited by another process, longer text")

    def test_external_write_same_size_new_mtime_is_seen(self) -> None:
        self.store.load()
        data = json.loads(self.store.path.read_text(encoding="utf-8"))
        data["settings"]["goal"] = "CALC"  # same length
        self.store.path.write_text(json.dumps(data), encoding="utf-8")
        st = self.store.path.stat()
        os.utime(self.store.path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000))
        self.assertEqual(self.store.load()["settings"]["goal"], "CALC")

    def test_transaction_updates_cache_and_revision(self) -> None:
        rev = self.store.load()["state_revision"]
        with self.store.transaction("change") as s:
            s["settings"]["goal"] = "new"
        st = self.store.load()
        self.assertEqual(st["settings"]["goal"], "new")
        self.assertEqual(st["state_revision"], rev + 1)

    def test_noop_transaction_writes_nothing(self) -> None:
        before = self.store.path.stat().st_mtime_ns
        rev = self.store.load()["state_revision"]
        with self.store.transaction("nothing"):
            pass
        self.assertEqual(self.store.load()["state_revision"], rev)
        self.assertEqual(self.store.path.stat().st_mtime_ns, before)

    def test_failed_transaction_leaves_cache_clean(self) -> None:
        with self.assertRaises(RuntimeError):
            with self.store.transaction("boom") as s:
                s["settings"]["goal"] = "half"
                raise RuntimeError("x")
        self.assertEqual(self.store.load()["settings"]["goal"], "calc")

    def test_deleted_file_gives_empty_state(self) -> None:
        self.store.load()
        self.store.path.unlink()
        self.assertEqual(self.store.load()["state_revision"], 0)

    def test_two_stores_same_folder_share_truth(self) -> None:
        other = ProjectStore(self.root)
        with other.transaction("other") as s:
            s["settings"]["goal"] = "from other"
        self.assertEqual(self.store.load()["settings"]["goal"], "from other")

    def test_migrate_state_default_still_copies(self) -> None:
        raw = {"db_version": 1, "settings": {}}
        out, _ = S.migrate_state(raw, "p")
        self.assertIsNot(out, raw)
        self.assertNotIn("tasks", raw)


class StoreBudgetTest(unittest.TestCase):
    """Performance budget on a realistic project (~600 KB, 2000 events): repeated reads stay cheap."""

    def test_repeated_load_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "big"
            root.mkdir()
            store = ProjectStore(root)
            with store.transaction("seed") as s:
                for i in range(40):
                    s["tasks"][f"TASK-{i:04d}"] = {"task_id": f"TASK-{i:04d}", "title": "t" * 200,
                                                   "acceptance_criteria": ["c" * 300] * 5}
            data = json.loads(store.path.read_text(encoding="utf-8"))
            ev = {"type": "task_status", "task_id": "TASK-0001", "why": "w" * 150, "state_revision": 1}
            data["events"] = [copy.deepcopy(ev) for _ in range(2000)]
            store.path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            store.load()  # warm
            n = 20
            t0 = time.perf_counter()
            for _ in range(n):
                store.load()
            per = (time.perf_counter() - t0) / n * 1000
            # generous for slow CI machines; before 5.16.0 this was ~20 ms on a fast machine
            self.assertLess(per, 15.0, f"cached load took {per:.1f} ms")


class LastGoodCopyTest(StoreCacheTest):
    def test_bf005_corrupt_state_offers_and_restores_last_good_copy(self) -> None:
        with self.store.transaction("second") as s:
            s["settings"]["goal"] = "calc v2"
            emit(s, "second")
        self.store.path.write_text('{"state_revision": ', encoding="utf-8")
        fresh = ProjectStore(self.root)
        with self.assertRaises(S.StoreError) as ctx:
            fresh.load()
        self.assertIn("state.json.prev", str(ctx.exception))
        self.assertNotIn("backups", str(ctx.exception))
        self.assertTrue(fresh.restore_last_good())
        self.assertEqual(fresh.load()["settings"]["goal"], "calc")
        self.assertTrue(any(p.name.startswith("state.corrupt-") for p in fresh.dir.iterdir()))

    def test_bf005_without_any_copy_the_message_does_not_invent_a_backup(self) -> None:
        self.store.prev_path.unlink(missing_ok=True)
        self.store.path.write_text("", encoding="utf-8")
        with self.assertRaises(S.StoreError) as ctx:
            ProjectStore(self.root).load()
        self.assertIn("No usable backup", str(ctx.exception))
        self.assertFalse(ProjectStore(self.root).restore_last_good())


if __name__ == "__main__":
    unittest.main()
