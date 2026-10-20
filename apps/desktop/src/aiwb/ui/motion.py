"""One animation clock for the whole application (roadmap 5.3.0, docs/design/DESIGN_LANGUAGE.md §6).

* :class:`Motion` drives every animation from a single timer at up to ``MOTION["fps"]`` frames per second and
  **sleeps** (no timer scheduled) whenever nothing moves.
* :meth:`Motion.tween` animates a value from ``a`` to ``b`` over ``ms`` with an easing; :meth:`Motion.loop` runs a
  slow live loop (active pulse, light particles) until it is stopped or its owner widget is gone.
* With ``reduced=True`` ("Reduce motion" in Settings) a tween jumps straight to its end state and loops are not
  started — the picture is the same, just still.
* The clock and the scheduler are injectable (``now`` / ``schedule`` / ``cancel``), so the engine is tested without
  Tk and without real time. Animations only change pixels; they never touch project data.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from .tokens5 import MOTION


# -- easing (t in 0..1)
def linear(t: float) -> float:
    return max(0.0, min(1.0, t))


def cubic_out(t: float) -> float:
    t = linear(t)
    return 1 - (1 - t) ** 3


def cubic_in_out(t: float) -> float:
    t = linear(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def pulse(t: float) -> float:
    """0 → 1 → 0 over one period, smooth at both ends (for breathing glows)."""
    t = linear(t)
    return 1 - (2 * t - 1) ** 2 if 0 <= t <= 1 else 0.0


EASINGS: dict[str, Callable[[float], float]] = {"linear": linear, "out": cubic_out, "in_out": cubic_in_out,
                                                 "pulse": pulse}


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class _Anim:
    __slots__ = ("key", "start", "ms", "a", "b", "ease", "on_step", "on_done", "loop", "alive")

    def __init__(self, key: str, start: float, ms: float, a: float, b: float, ease: Callable[[float], float],
                 on_step: Callable[[float], Any], on_done: Callable[[], Any] | None, loop: bool,
                 alive: Callable[[], bool] | None) -> None:
        self.key, self.start, self.ms, self.a, self.b = key, start, max(1.0, ms), a, b
        self.ease, self.on_step, self.on_done, self.loop, self.alive = ease, on_step, on_done, loop, alive


class Motion:
    """The animation clock. ``schedule(ms, fn) -> handle`` and ``cancel(handle)`` default to Tk's ``after``."""

    def __init__(self, root: Any = None, *, reduced: bool = False, fps: int | None = None,
                 now: Callable[[], float] | None = None, schedule: Callable[[int, Callable[[], None]], Any] | None = None,
                 cancel: Callable[[Any], None] | None = None) -> None:
        self.root = root
        self.reduced = reduced
        self.fps = int(fps or MOTION["fps"])
        self.frame_ms = max(1, round(1000 / self.fps))
        self._now = now or (lambda: time.monotonic() * 1000.0)
        self._schedule = schedule or (lambda ms, fn: root.after(ms, fn))
        self._cancel = cancel or (lambda h: root.after_cancel(h))
        self.anims: dict[str, _Anim] = {}
        self._timer: Any = None
        self.frames = 0                 # frames run since creation (for tests and the speed gate)
        self.frame_cost_ms: list[float] = []   # wall time spent inside recent frames

    # -- public
    @property
    def running(self) -> bool:
        """True while a frame is scheduled; False means the clock sleeps."""
        return self._timer is not None

    def set_reduced(self, reduced: bool) -> None:
        self.reduced = bool(reduced)
        if self.reduced:
            self.finish_all()

    def tween(self, key: str, a: float, b: float, ms: float, on_step: Callable[[float], Any], *,
              ease: str | Callable[[float], float] = "out", on_done: Callable[[], Any] | None = None,
              alive: Callable[[], bool] | None = None) -> None:
        """Animate ``a`` → ``b``. A new tween with the same ``key`` replaces the old one (starting where it is)."""
        fn = EASINGS[ease] if isinstance(ease, str) else ease
        if self.reduced or ms <= 0:
            self.anims.pop(key, None)
            self._safe(on_step, b)
            if on_done is not None:
                self._safe(on_done)
            return
        self.anims[key] = _Anim(key, self._now(), ms, a, b, fn, on_step, on_done, False, alive)
        self._safe(on_step, a)
        self._wake()

    def loop(self, key: str, period_ms: float, on_step: Callable[[float], Any], *,
             alive: Callable[[], bool] | None = None) -> bool:
        """Run ``on_step(phase)`` with phase 0..1 repeating every ``period_ms`` until :meth:`stop`. Not when reduced."""
        if self.reduced:
            return False
        if key in self.anims and self.anims[key].loop:
            return True
        self.anims[key] = _Anim(key, self._now(), period_ms, 0.0, 1.0, linear, on_step, None, True, alive)
        self._wake()
        return True

    def stop(self, key: str, *, finish: bool = False) -> None:
        an = self.anims.pop(key, None)
        if an is not None and finish and not an.loop:
            self._safe(an.on_step, an.b)
            if an.on_done is not None:
                self._safe(an.on_done)
        if not self.anims:
            self._sleep()

    def stop_prefix(self, prefix: str) -> None:
        for k in [k for k in self.anims if k.startswith(prefix)]:
            self.anims.pop(k, None)
        if not self.anims:
            self._sleep()

    def finish_all(self) -> None:
        """Jump every tween to its end state and stop every loop (Reduce motion, window closing)."""
        for an in list(self.anims.values()):
            if not an.loop:
                self._safe(an.on_step, an.b)
                if an.on_done is not None:
                    self._safe(an.on_done)
        self.anims.clear()
        self._sleep()

    def active(self, key: str) -> bool:
        return key in self.anims

    # -- clock
    def _wake(self) -> None:
        if self._timer is None and self.anims:
            self._timer = self._schedule(self.frame_ms, self._frame)

    def _sleep(self) -> None:
        if self._timer is not None:
            try:
                self._cancel(self._timer)
            except Exception:  # noqa: BLE001 - the root may already be gone
                pass
            self._timer = None

    def _frame(self) -> None:
        self._timer = None
        t0 = time.perf_counter()
        now = self._now()
        self.frames += 1
        for key, an in list(self.anims.items()):
            if self.anims.get(key) is not an:
                continue
            if an.alive is not None and not self._alive(an):
                self.anims.pop(key, None)
                continue
            el = now - an.start
            if an.loop:
                if not self._safe(an.on_step, (el % an.ms) / an.ms):
                    self.anims.pop(key, None)
                continue
            t = min(1.0, el / an.ms)
            ok = self._safe(an.on_step, lerp(an.a, an.b, an.ease(t)))
            if t >= 1.0 or not ok:
                self.anims.pop(key, None)
                if ok and an.on_done is not None:
                    self._safe(an.on_done)
        self.frame_cost_ms.append((time.perf_counter() - t0) * 1000.0)
        del self.frame_cost_ms[:-120]
        if self.anims:
            self._timer = self._schedule(self.frame_ms, self._frame)

    @staticmethod
    def _alive(an: _Anim) -> bool:
        try:
            return bool(an.alive())  # type: ignore[misc]
        except Exception:  # noqa: BLE001 - a destroyed widget means the animation is over
            return False

    @staticmethod
    def _safe(fn: Callable[..., Any], *args: Any) -> bool:
        """Run one animation callback; a widget destroyed mid-animation ends that animation, never the app."""
        try:
            fn(*args)
            return True
        except Exception:  # noqa: BLE001 - TclError on destroyed widgets and the like
            return False


def value_text(a: float, b: float, t: float, fmt: str = "{:.0f}") -> str:
    """Counter text for a status-bar number moving from ``a`` to ``b`` at eased time ``t``."""
    return fmt.format(lerp(a, b, cubic_out(t)))
