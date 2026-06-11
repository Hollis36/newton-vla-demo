"""Tests for the two-arm collaborative tower build (collab.CollaborativeBuild).

Arm A (mobile) fetches field blocks to a handoff slot; Arm B (fixed) picks from
the slot and stacks a tower; then the roles reverse to tear it down, and it
loops. These tests drive the coordinator with a deterministic clock so the
wall-clock easing in the executors advances at a fixed rate — fast and
repeatable rather than waiting real seconds.
"""

from __future__ import annotations

import contextlib
import io
import time
import unittest

from demo_live.collab import HANDOFF_X, TOWER_X, CollaborativeBuild
from demo_live.control import FKJointController, JointController
from demo_live.physics import BLOCK_HALF, FKArmRig, World
from demo_live.tasks import TaskExecutor

ARM_B_ANCHOR_X = 2.40


class _Clock:
    """Deterministic monotonic clock — ticked 1/60 s per frame so the executors'
    perf_counter-based easing is repeatable and runs as fast as the loop."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def tick(self) -> None:
        self.t += 1.0 / 60.0


@contextlib.contextmanager
def _quiet():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _build_arms(world: World):
    ctrl_a = JointController(world)
    exe_a = TaskExecutor(world, ctrl_a, label="A")
    rig = FKArmRig(anchor_world_x=ARM_B_ANCHOR_X)
    ctrl_b = FKJointController(rig)
    exe_b = TaskExecutor(
        world, ctrl_b, label="B",
        anchor_world_x=lambda: rig.anchor_world_x,
        arm_state_provider=rig.arm_state_from_target,
    )
    return (ctrl_a, exe_a), (ctrl_b, exe_b)


def _pump(world, a, b, collab, clock, *, max_frames, until):
    (ctrl_a, exe_a), (ctrl_b, exe_b) = a, b
    for _ in range(max_frames):
        collab.update()
        exe_a.update(1 / 60)
        ctrl_a.update(1 / 60)
        exe_b.update(1 / 60)
        ctrl_b.update(1 / 60)
        world.step()
        clock.tick()
        if until():
            return True
    return False


class _StubBlock:
    def __init__(self, xz: tuple[float, float]) -> None:
        self.xz = xz


class _StubWorld:
    """Just enough of World for CollaborativeBuild: find_block with .xz."""

    def __init__(self, layout: dict[str, tuple[float, float]]) -> None:
        self._blocks = {c: _StubBlock(xz) for c, xz in layout.items()}

    def find_block(self, color: str):
        return self._blocks.get(color)


class _StubExecutor:
    """Records queued programs and stays busy for a fixed number of ticks, so
    the coordinator's hand-off gating can be exercised without physics."""

    BUSY_TICKS = 3

    def __init__(self, label: str) -> None:
        self.label = label
        self.busy = False
        self.programs: list[list] = []
        self._countdown = 0

    def make_pick(self, color: str) -> list:
        return [("pick", color)]

    def make_place(self, dest: tuple[float, float]) -> list:
        return [("place", dest)]

    def queue(self, program: list) -> None:
        self.programs.append(program)
        self.busy = True
        self._countdown = self.BUSY_TICKS

    def tick(self) -> None:
        if self.busy:
            self._countdown -= 1
            if self._countdown <= 0:
                self.busy = False


class CollabStateMachineTest(unittest.TestCase):
    """Drives the coordinator with stub executors — covers the phases the
    physics-backed test can't afford to reach: teardown ordering, the admire
    hold, and the build → teardown → build loop."""

    COLORS = ("red", "green", "blue")
    HOMES = {"red": (0.70, 0.10), "green": (1.10, 0.10), "blue": (1.50, 0.10)}

    def setUp(self):
        self._real_perf = time.perf_counter
        self.clock = _Clock()
        time.perf_counter = self.clock
        self.world = _StubWorld(dict(self.HOMES))
        self.exe_a = _StubExecutor("A")
        self.exe_b = _StubExecutor("B")
        from demo_live.collab import CollaborativeBuild as CB
        self.collab = CB(self.world, self.exe_a, self.exe_b, colors=self.COLORS)

    def tearDown(self):
        time.perf_counter = self._real_perf

    def _pump(self, *, until, max_frames=2000) -> bool:
        for _ in range(max_frames):
            self.collab.update()
            self.exe_a.tick()
            self.exe_b.tick()
            self.clock.tick()
            if until():
                return True
        return False

    def test_build_queues_ascending_tower_and_completes(self):
        done = self._pump(until=lambda: self.collab.tower_complete)
        self.assertTrue(done)
        # Arm A delivered all three to the handoff slot, in order.
        picks_a = [step[1] for prog in self.exe_a.programs for step in prog
                   if step[0] == "pick"]
        self.assertEqual(picks_a, list(self.COLORS))
        # Arm B stacked at the tower column with ascending z.
        dests_b = [step[1] for prog in self.exe_b.programs for step in prog
                   if step[0] == "place"]
        self.assertEqual([d[0] for d in dests_b], [TOWER_X] * 3)
        zs = [d[1] for d in dests_b]
        self.assertEqual(zs, sorted(zs))

    def test_admire_hold_then_teardown_reverses_roles_and_order(self):
        self._pump(until=lambda: self.collab.tower_complete)
        a_progs, b_progs = len(self.exe_a.programs), len(self.exe_b.programs)
        # During the admire hold nothing new is queued.
        for _ in range(30):  # 0.5 s of the 2.5 s hold
            self.collab.update()
            self.clock.tick()
        self.assertEqual(len(self.exe_a.programs), a_progs)
        self.assertEqual(len(self.exe_b.programs), b_progs)
        # After the hold the coordinator flips to teardown, top block first.
        self._pump(until=lambda: self.collab.phase == "teardown")
        self._pump(until=lambda: len(self.exe_b.programs) > b_progs)
        first_teardown_pick = self.exe_b.programs[b_progs][0]
        self.assertEqual(first_teardown_pick, ("pick", "blue"),
                         "teardown must remove the top block first")

    def test_teardown_returns_blocks_home_then_loops_to_build(self):
        self._pump(until=lambda: self.collab.tower_complete)
        a_progs = len(self.exe_a.programs)
        self._pump(until=lambda: self.collab.phase == "teardown")
        # Run the teardown to completion: the loop flips back to "build".
        looped = self._pump(
            until=lambda: self.collab.phase == "build"
            and len(self.exe_a.programs) > a_progs + len(self.COLORS) - 1,
        )
        self.assertTrue(looped, "coordinator should loop back to building")
        # Arm A carried each block back to its spawn slot during teardown.
        teardown_dests = [
            step[1]
            for prog in self.exe_a.programs[a_progs:a_progs + len(self.COLORS)]
            for step in prog if step[0] == "place"
        ]
        self.assertEqual(
            teardown_dests,
            [self.HOMES[c] for c in reversed(self.COLORS)],
            "teardown must return blocks to their original slots, top first",
        )


class CollaborativeBuildTest(unittest.TestCase):
    def setUp(self):
        self._real_perf = time.perf_counter
        self.clock = _Clock()
        time.perf_counter = self.clock

    def tearDown(self):
        time.perf_counter = self._real_perf

    def test_build_phase_stacks_a_tower_in_arm_b_zone(self):
        colors = ["red", "green", "blue"]
        with _quiet():
            world = World(real_blocks=True)
            a, b = _build_arms(world)
            for _ in range(20):
                world.step()
            collab = CollaborativeBuild(world, a[1], b[1], colors=colors)
            done = _pump(world, a, b, collab, self.clock,
                         max_frames=60 * 240, until=lambda: collab.tower_complete)

        self.assertTrue(done, "collaborative build did not finish the tower in time")
        zs = sorted(world.find_block(c).xz[1] for c in colors)
        self.assertAlmostEqual(zs[0], BLOCK_HALF, delta=0.06)
        self.assertAlmostEqual(zs[1], 3 * BLOCK_HALF, delta=0.08)
        self.assertAlmostEqual(zs[2], 5 * BLOCK_HALF, delta=0.10)
        # All three stacked at the tower column in Arm B's zone.
        for c in colors:
            self.assertAlmostEqual(world.find_block(c).xz[0], TOWER_X, delta=0.18,
                                   msg=f"{c} not over the tower column")

    def test_handoff_and_tower_are_reachable_by_arm_b(self):
        # Arm B is fixed at x=2.40; both the handoff slot and the tower column
        # must sit inside its proven reach band (the workpiece shuttle covers
        # 1.50..2.50), or B can never pick/stack.
        self.assertGreaterEqual(HANDOFF_X, 1.45)
        self.assertLessEqual(TOWER_X, 2.50)
        self.assertGreater(abs(TOWER_X - HANDOFF_X), 2 * BLOCK_HALF * 0.5)


if __name__ == "__main__":
    unittest.main()
