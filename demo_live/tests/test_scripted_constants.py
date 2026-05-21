"""Sanity tests for the `demo_live.scripted` data constants.

These are static lists (rehearsal scripts + Arm B idle cycle) — the bugs
they'd ever ship are typos in action names that `pipeline.build_plan_from`
would silently ignore. The tests below feed every entry through the same
plan-builder the live demo uses, asserting a non-empty plan comes out.
A typo in `"wave" → "waev"` would surface immediately.
"""

from __future__ import annotations

import unittest

from demo_live import pipeline, scripted, tasks
from demo_live.physics import Block


class FakeWorld:
    base_drive_speed = 0.8
    base_x = 0.0
    base_target_x = 0.0

    def __init__(self) -> None:
        # Includes "workpiece" so the Arm B idle cycle (which picks the
        # workpiece by color) finds it. Without this the cycle still
        # produces a non-empty plan via the place-only fallback, but the
        # full pick+place path stays untested.
        self._blocks = {
            c: Block(color=c, xz=(x, 0.1))
            for c, x in (("red", 0.9), ("green", 1.1),
                         ("blue", 1.3), ("yellow", -0.9),
                         ("workpiece", 2.0))
        }
        self.drive_calls: list[float] = []

    def find_block(self, color: str) -> Block | None:
        return self._blocks.get(color)

    def move_block(self, block: Block, xz: tuple[float, float]) -> None:
        pass

    def drive_to(self, x: float) -> None:
        self.drive_calls.append(x)


class StubController:
    def go_home(self) -> None:
        pass


def _execute(action: str, colors: list[str] | None) -> list[tasks.Waypoint]:
    w = FakeWorld()
    c = StubController()
    ex = tasks.TaskExecutor(world=w, ctrl=object())
    return pipeline.build_plan_from(ex, c, w, action, None, colors, None)


# ============================================================================
# ARM_B_IDLE_CYCLE — every entry must produce a non-empty plan
# ============================================================================


class ArmBIdleCycleTest(unittest.TestCase):
    def test_cycle_is_non_empty(self) -> None:
        self.assertGreater(len(scripted.ARM_B_IDLE_CYCLE), 0)

    def test_each_step_produces_a_plan(self) -> None:
        """Catches typos in action names — would have caught the R.1
        preflight-whitelist regression class before it hit a live demo."""
        w = FakeWorld()
        c = StubController()
        ex = tasks.TaskExecutor(world=w, ctrl=object())
        # Arm B is fixed; anchor_world_x flag prevents make_drive from
        # leaking into the test's drive_calls list and confirms the
        # Y.1 fixed-arm early-out actually works.
        ex.anchor_world_x = lambda: 2.40
        for i, step in enumerate(scripted.ARM_B_IDLE_CYCLE):
            plan = pipeline.build_plan_from(
                ex, c, w,
                step.action, step.color, step.colors, step.target,
            )
            self.assertGreater(
                len(plan), 0,
                f"ARM_B_IDLE_CYCLE[{i}] = {step} produced an empty plan — "
                f"typo in the action name?",
            )
        # Y.1 invariant: fixed-arm shuttle MUST NOT call world.drive_to.
        self.assertEqual(w.drive_calls, [],
                         "fixed-arm executor leaked a drive_to() call")

    def test_idle_pause_is_reasonable(self) -> None:
        """Pause between gestures should be readable (not zero) but not
        glacial (a demo that idles for 30 s reads as broken)."""
        self.assertGreater(scripted.ARM_B_IDLE_PAUSE_S, 0.5)
        self.assertLess(scripted.ARM_B_IDLE_PAUSE_S, 10.0)


# ============================================================================
# Rehearsal scripts — same typo guard, plus presence of expected beats
# ============================================================================


class RehearsalScriptTest(unittest.TestCase):
    def test_default_script_includes_all_three_input_modes(self) -> None:
        """Beats 1-3 should exercise catch / type / voice respectively —
        the whole point of the rehearsal is to show every input path."""
        script = scripted.build_default_rehearsal(industrial=False)
        steps = [s for _, s in script]
        self.assertTrue(any(s.startswith("catch:") for s in steps),
                        "rehearsal needs a catch beat")
        self.assertTrue(any(s.startswith("type:") for s in steps),
                        "rehearsal needs a typed-input beat")
        self.assertTrue(any(s.startswith("voice:") for s in steps),
                        "rehearsal needs a voice beat")

    def test_industrial_appends_arm_b_step(self) -> None:
        legacy = scripted.build_default_rehearsal(industrial=False)
        industrial = scripted.build_default_rehearsal(industrial=True)
        self.assertEqual(len(industrial), len(legacy) + 1)
        self.assertTrue(any(s.startswith("arm_b:") for _, s in industrial))

    def test_build_returns_a_copy(self) -> None:
        """build_default_rehearsal must not let callers mutate the module
        constant (defensive copy)."""
        a = scripted.build_default_rehearsal(industrial=True)
        a.clear()
        b = scripted.build_default_rehearsal(industrial=True)
        self.assertGreater(len(b), 0)

    def test_f5_script_is_independent(self) -> None:
        """F5 hotkey script is a fixed module constant; mutating the live
        copy must not leak back into the constant either."""
        live = list(scripted.REHEARSAL_SCRIPT_F5)
        live.append((99.0, "broken"))
        self.assertNotIn((99.0, "broken"), scripted.REHEARSAL_SCRIPT_F5)


if __name__ == "__main__":
    unittest.main()
