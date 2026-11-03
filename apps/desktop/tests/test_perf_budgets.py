"""Roadmap 5.20.0: the 5.16.0 performance budgets (R2) as permanent tests.

Gate of 5.16.0, on a large state (~560 KB, 40 tasks, 2000 events):

* a repeated (cached) ``load()`` of the state takes at most 5 ms;
* one real transaction (read + change + validate + atomic write with fsync) takes at most 40 ms;
* a no-op transaction does not rewrite the file.

The median of several runs is compared, so one slow tick of the machine does not fail the test. On CI runners
(``CI`` is set by GitHub Actions) the budget gets a x2 margin because shared runners and Windows fsync are slower;
on the owner's machine the strict numbers apply. The other 5.16.0 budgets are already permanent:
menu raster (``test_raster_9slice``), animation frame cost (``test_motion``), zero idle frames and menus that close
(``tests/gui/gui_v516_light_smoke.py``).
"""
from __future__ import annotations

import copy
import json
import os
import statistics
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.v2.store import ProjectStore  # noqa: E402

LOAD_BUDGET_MS = 5.0
TRANSACTION_BUDGET_MS = 40.0
SLACK = 2.0 if os.environ.get("CI") else 1.0


def _big_store(base: Path) -> ProjectStore:
    root = base / "big"
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
    store.load()  # warm the cache
    return store


def _median_ms(fn, runs: int) -> float:
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


class PerfBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = _big_store(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_state_is_large(self) -> None:
        size = self.store.path.stat().st_size
        self.assertGreater(size, 400_000, f"the budget state should be large (~560 KB), got {size // 1024} KB")

    def test_cached_load_budget(self) -> None:
        per = _median_ms(self.store.load, 30)
        limit = LOAD_BUDGET_MS * SLACK
        self.assertLessEqual(per, limit, f"cached load took {per:.2f} ms (budget {limit:.0f} ms)")

    def test_transaction_budget(self) -> None:
        counter = iter(range(10_000))

        def one() -> None:
            with self.store.transaction("budget") as s:
                s["tasks"]["TASK-0001"]["title"] = f"changed {next(counter)}"

        one()  # warm
        per = _median_ms(one, 9)
        limit = TRANSACTION_BUDGET_MS * SLACK
        self.assertLessEqual(per, limit, f"one transaction took {per:.1f} ms (budget {limit:.0f} ms)")

    def test_noop_transaction_does_not_write(self) -> None:
        before = self.store.path.stat().st_mtime_ns
        rev = self.store.revision()
        time.sleep(0.01)
        with self.store.transaction("nothing") as s:
            _ = s["tasks"]["TASK-0002"]["title"]
        self.assertEqual(self.store.path.stat().st_mtime_ns, before, "a no-op transaction rewrote state.json")
        self.assertEqual(self.store.revision(), rev)


if __name__ == "__main__":
    unittest.main()
