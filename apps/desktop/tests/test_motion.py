"""Roadmap 5.3.0: the animation engine — timing, easing, auto-sleep, frame budget, reduce motion (no Tk)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.ui import motion  # noqa: E402


class FakeClock:
    """Deterministic time + scheduler: ``advance(ms)`` runs every due frame."""

    def __init__(self) -> None:
        self.t = 0.0
        self.queue: list[tuple[float, int, object]] = []
        self.n = 0

    def now(self) -> float:
        return self.t

    def schedule(self, ms: int, fn) -> int:
        self.n += 1
        self.queue.append((self.t + ms, self.n, fn))
        return self.n

    def cancel(self, h: int) -> None:
        self.queue = [q for q in self.queue if q[1] != h]

    def advance(self, ms: float) -> None:
        end = self.t + ms
        while True:
            due = sorted(q for q in self.queue if q[0] <= end)
            if not due:
                break
            at, h, fn = due[0]
            self.queue.remove(due[0])
            self.t = at
            fn()
        self.t = end


def make(reduced: bool = False) -> tuple[motion.Motion, FakeClock]:
    c = FakeClock()
    return motion.Motion(None, reduced=reduced, now=c.now, schedule=c.schedule, cancel=c.cancel), c


class EasingTests(unittest.TestCase):
    def test_ends_and_monotonic(self) -> None:
        for name in ("linear", "out", "in_out"):
            f = motion.EASINGS[name]
            self.assertAlmostEqual(f(0), 0.0)
            self.assertAlmostEqual(f(1), 1.0)
            vals = [f(i / 50) for i in range(51)]
            self.assertEqual(vals, sorted(vals), name)
        self.assertGreater(motion.cubic_out(0.25), 0.25)  # entering: fast start
        self.assertLess(motion.cubic_in_out(0.25), 0.25)  # moving: gentle start
        self.assertAlmostEqual(motion.cubic_in_out(0.5), 0.5)
        self.assertEqual(motion.linear(-1), 0.0)
        self.assertEqual(motion.linear(2), 1.0)

    def test_pulse(self) -> None:
        self.assertAlmostEqual(motion.pulse(0), 0.0)
        self.assertAlmostEqual(motion.pulse(0.5), 1.0)
        self.assertAlmostEqual(motion.pulse(1), 0.0)

    def test_value_text(self) -> None:
        self.assertEqual(motion.value_text(0, 5, 0), "0")
        self.assertEqual(motion.value_text(0, 5, 1), "5")


class TweenTests(unittest.TestCase):
    def test_tween_reaches_end_on_time_and_clock_sleeps(self) -> None:
        m, c = make()
        seen: list[float] = []
        done: list[bool] = []
        m.tween("x", 0, 100, 240, seen.append, on_done=lambda: done.append(True))
        self.assertTrue(m.running)
        self.assertEqual(seen[0], 0)
        c.advance(120)
        self.assertTrue(0 < seen[-1] < 100)
        self.assertFalse(done)
        c.advance(140)
        self.assertEqual(seen[-1], 100)
        self.assertEqual(done, [True])
        self.assertFalse(m.running, "the clock must sleep when nothing moves")
        self.assertEqual(c.queue, [])
        frames = m.frames
        c.advance(1000)
        self.assertEqual(m.frames, frames, "no frames while idle")

    def test_frame_rate(self) -> None:
        m, c = make()
        m.tween("x", 0, 1, 1000, lambda _v: None, ease="linear")
        c.advance(1000 + m.frame_ms)
        self.assertTrue(55 <= m.frames <= 64, m.frames)

    def test_same_key_replaces(self) -> None:
        m, c = make()
        a: list[float] = []
        b: list[float] = []
        m.tween("k", 0, 10, 200, a.append)
        c.advance(50)
        m.tween("k", 5, 0, 100, b.append)
        c.advance(300)
        self.assertEqual(b[-1], 0)
        n = len(a)
        c.advance(300)
        self.assertEqual(len(a), n)
        self.assertEqual(len(m.anims), 0)

    def test_stop_and_finish(self) -> None:
        m, c = make()
        v: list[float] = []
        m.tween("k", 0, 10, 500, v.append)
        m.stop("k", finish=True)
        self.assertEqual(v[-1], 10)
        self.assertFalse(m.running)
        m.tween("a", 0, 1, 500, v.append)
        m.tween("b", 0, 2, 500, v.append)
        m.finish_all()
        self.assertEqual(sorted(v[-2:]), [1, 2])
        self.assertFalse(m.running)

    def test_failing_callback_ends_only_that_animation(self) -> None:
        m, c = make()
        ok: list[float] = []

        def boom(_v: float) -> None:
            raise RuntimeError("widget destroyed")
        m.tween("bad", 0, 1, 200, boom)
        m.tween("good", 0, 1, 200, ok.append)
        c.advance(300)
        self.assertEqual(ok[-1], 1)
        self.assertFalse(m.running)

    def test_alive_guard(self) -> None:
        m, c = make()
        alive = [True]
        v: list[float] = []
        m.tween("k", 0, 1, 500, v.append, alive=lambda: alive[0])
        c.advance(50)
        alive[0] = False
        n = len(v)
        c.advance(100)
        self.assertEqual(len(v), n)
        self.assertFalse(m.running)


class LoopTests(unittest.TestCase):
    def test_loop_runs_until_stopped(self) -> None:
        m, c = make()
        phases: list[float] = []
        self.assertTrue(m.loop("pulse", 1600, phases.append))
        self.assertTrue(m.loop("pulse", 1600, phases.append))  # idempotent
        c.advance(3300)
        self.assertTrue(all(0 <= p < 1 for p in phases))
        self.assertTrue(any(p < 0.1 for p in phases[60:]), "the phase wraps around")
        self.assertTrue(m.running)
        m.stop("pulse")
        self.assertFalse(m.running)

    def test_stop_prefix(self) -> None:
        m, c = make()
        m.loop("mission:pulse:a", 1000, lambda _p: None)
        m.loop("mission:pulse:b", 1000, lambda _p: None)
        m.loop("other", 1000, lambda _p: None)
        m.stop_prefix("mission:")
        self.assertEqual(list(m.anims), ["other"])


class ReduceMotionTests(unittest.TestCase):
    def test_reduced_jumps_to_end_and_never_schedules(self) -> None:
        m, c = make(reduced=True)
        v: list[float] = []
        done: list[bool] = []
        m.tween("k", 0, 10, 500, v.append, on_done=lambda: done.append(True))
        self.assertEqual(v, [10])
        self.assertEqual(done, [True])
        self.assertFalse(m.loop("pulse", 1600, v.append))
        self.assertFalse(m.running)
        self.assertEqual(c.queue, [])

    def test_switching_on_finishes_running_animations(self) -> None:
        m, c = make()
        v: list[float] = []
        m.tween("k", 0, 10, 500, v.append)
        m.loop("p", 1000, lambda _p: None)
        m.set_reduced(True)
        self.assertEqual(v[-1], 10)
        self.assertFalse(m.anims)
        self.assertFalse(m.running)


class BudgetTests(unittest.TestCase):
    def test_frame_cost_is_recorded_and_small(self) -> None:
        m, c = make()
        for i in range(40):
            m.tween(f"k{i}", 0, 1, 500, lambda _v: None)
        c.advance(600)
        self.assertTrue(m.frame_cost_ms)
        self.assertLess(max(m.frame_cost_ms), 16.0, "40 tweens must fit well inside one 60 fps frame")


if __name__ == "__main__":
    unittest.main()
