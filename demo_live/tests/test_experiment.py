"""Tests for Arm B's offset-tower stability experiment (experiment.py).

Two layers:
- A stub-driven state machine suite (build order, verdict, cleanup, round
  schedule, CoM overlay math) that runs in milliseconds.
- A real-physics pin: the offset schedule's bracketing claim — 4 cm/layer
  survives, 9 cm/layer genuinely topples under XPBD — asserted on a real
  World so a future solver retune can't silently break the show's climax.
"""

from __future__ import annotations

import contextlib
import io
import time
import unittest

from demo_live.experiment import (
    OFFSET_SCHEDULE,
    SETTLE_S,
    TOPPLE_ANGLE_RAD,
    VERDICT_HOLD_S,
    StabilityExperiment,
)
from demo_live.physics import BLOCK_HALF


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def tick(self, dt: float = 1 / 60) -> None:
        self.t += dt


class _StubBlock:
    def __init__(self, xz: tuple[float, float]) -> None:
        self.xz = xz
        self.angle = 0.0


class _StubWorld:
    def __init__(self, layout: dict[str, tuple[float, float]]) -> None:
        self.blocks = {c: _StubBlock(xz) for c, xz in layout.items()}

    def find_block(self, color: str):
        return self.blocks.get(color)


class _StubExecutor:
    """Stays busy a fixed number of ticks per program; on completion, moves
    the picked block to the placed destination so the coordinator's
    real-pose queries (toppled / com_overlay) see the stack grow."""

    BUSY_TICKS = 3

    def __init__(self, world: _StubWorld) -> None:
        self.world = world
        self.busy = False
        self.programs: list[list] = []
        self._countdown = 0
        self._pending: tuple[str, tuple[float, float]] | None = None

    def make_pick(self, color: str) -> list:
        return [("pick", color)]

    def make_place(self, dest: tuple[float, float]) -> list:
        return [("place", dest)]

    def queue(self, program: list) -> None:
        self.programs.append(program)
        color = next(s[1] for s in program if s[0] == "pick")
        dest = next(s[1] for s in program if s[0] == "place")
        self._pending = (color, dest)
        self.busy = True
        self._countdown = self.BUSY_TICKS

    def tick(self) -> None:
        if self.busy:
            self._countdown -= 1
            if self._countdown <= 0:
                color, dest = self._pending
                self.world.blocks[color].xz = dest
                self.busy = False


COLORS = ("workpiece", "slate", "zinc")
HOMES = {"workpiece": (2.00, 0.10), "slate": (1.80, 0.10), "zinc": (2.20, 0.10)}


class StateMachineTest(unittest.TestCase):
    def setUp(self):
        self._real_perf = time.perf_counter
        self.clock = _Clock()
        time.perf_counter = self.clock
        self.world = _StubWorld(dict(HOMES))
        self.exe = _StubExecutor(self.world)
        self.events: list[tuple[str, str]] = []
        self.exp = StabilityExperiment(
            self.world, self.exe, colors=COLORS,
            on_event=lambda kind, text: self.events.append((kind, text)),
        )

    def tearDown(self):
        time.perf_counter = self._real_perf

    def _pump(self, *, until, max_frames=5000) -> bool:
        for _ in range(max_frames):
            self.exp.update()
            self.exe.tick()
            self.clock.tick()
            if until():
                return True
        return False

    def test_round1_builds_aligned_tower_in_order(self):
        self.assertTrue(self._pump(until=lambda: self.exp.phase == "observe"))
        dests = [next(s[1] for s in p if s[0] == "place") for p in self.exe.programs]
        self.assertEqual([d[0] for d in dests], [self.exp.column_x] * 3,
                         "round 1 offset is 0 — all layers on the column")
        self.assertEqual([d[1] for d in dests],
                         [BLOCK_HALF, 3 * BLOCK_HALF, 5 * BLOCK_HALF])
        picks = [next(s[1] for s in p if s[0] == "pick") for p in self.exe.programs]
        self.assertEqual(picks, list(COLORS))

    def test_stable_round_graduates_to_bigger_offset(self):
        self._pump(until=lambda: self.exp.phase == "observe")
        self.clock.tick(SETTLE_S + 0.1)
        self.exp.update()  # verdict: stub blocks stand upright -> stable
        self.assertEqual(self.events[-1][0], "stable")
        self.clock.tick(VERDICT_HOLD_S + 0.1)
        self.exp.update()  # -> cleanup
        self.assertTrue(self._pump(until=lambda: self.exp.phase == "build"))
        self.assertEqual(self.exp.round_idx, 1)
        # Cleanup returned every block to its spawn slot.
        cleanup_dests = [next(s[1] for s in p if s[0] == "place")
                         for p in self.exe.programs[3:6]]
        self.assertEqual(cleanup_dests, [HOMES[c] for c in COLORS])
        # Round 2 layers step toward -x by the next offset in the schedule.
        self._pump(until=lambda: self.exp.phase == "observe")
        d = OFFSET_SCHEDULE[1]
        dests = [next(s[1] for s in p if s[0] == "place")
                 for p in self.exe.programs[6:9]]
        for i, dest in enumerate(dests):
            self.assertAlmostEqual(dest[0], self.exp.column_x - i * d, places=6)

    def test_toppled_round_restarts_schedule(self):
        self.exp.round_idx = 2
        self.exp._begin_build()
        self._pump(until=lambda: self.exp.phase == "observe")
        self.world.blocks["zinc"].angle = 0.6  # knocked well past the verdict angle
        self.clock.tick(SETTLE_S + 0.1)
        self.exp.update()
        self.assertEqual(self.events[-1][0], "topple")
        self.clock.tick(VERDICT_HOLD_S + 0.1)
        self.exp.update()
        self.assertTrue(self._pump(until=lambda: self.exp.phase == "build"))
        self.assertEqual(self.exp.round_idx, 0, "collapse restarts the lecture")

    def test_com_overlay_tracks_real_poses(self):
        self.assertIsNone(self.exp.com_overlay(), "nothing stacked yet")
        self._pump(until=lambda: self.exp.phase == "observe")
        com_x, base_min, base_max, stable = self.exp.com_overlay()
        self.assertAlmostEqual(com_x, self.exp.column_x, places=6)
        self.assertAlmostEqual(base_min, self.exp.column_x - BLOCK_HALF, places=6)
        self.assertAlmostEqual(base_max, self.exp.column_x + BLOCK_HALF, places=6)
        self.assertTrue(stable)
        # Push the top block sideways past the criterion: overlay flips.
        self.world.blocks["zinc"].xz = (self.exp.column_x - 3.2 * BLOCK_HALF,
                                        5 * BLOCK_HALF)
        com_x, _, _, stable = self.exp.com_overlay()
        self.assertLess(com_x, self.exp.column_x - BLOCK_HALF)
        self.assertFalse(stable)

    def test_overlay_flips_on_top_two_com_at_nine_cm_round(self):
        """The 9 cm round: all-layers mean excursion is 9 cm (< r = 10 cm),
        but the load resting on the bottom block (top two layers) has its CoM
        at 1.5*9 = 13.5 cm > r — so the overlay must flip amber, matching the
        physical topple and the lecture's criterion. A regression guard
        against reverting to the all-layers-mean (which never flips here)."""
        self.exp.round_idx = OFFSET_SCHEDULE.index(0.09)
        self.exp._begin_build()
        self.assertTrue(self._pump(until=lambda: self.exp.phase == "observe"))
        com_x, _, _, stable = self.exp.com_overlay()
        base = self.exp.column_x
        self.assertAlmostEqual(com_x, base - 1.5 * 0.09, places=6,
                               msg="overlay CoM must be the top-two-layer CoM (1.5*offset)")
        self.assertFalse(stable, "13.5 cm > 10 cm support — overlay must be amber")

    def test_overlay_stable_at_four_cm_round(self):
        """The 4 cm round survives: top-two CoM at 1.5*4 = 6 cm < r, green."""
        self.exp.round_idx = OFFSET_SCHEDULE.index(0.04)
        self.exp._begin_build()
        self.assertTrue(self._pump(until=lambda: self.exp.phase == "observe"))
        _, _, _, stable = self.exp.com_overlay()
        self.assertTrue(stable, "6 cm < 10 cm support — overlay stays green")

    def test_topple_detector_also_catches_fallen_top_block(self):
        self._pump(until=lambda: self.exp.phase == "observe")
        # No tilt, but the top block dropped to the ground (slid off cleanly).
        self.world.blocks["zinc"].xz = (self.exp.column_x - 0.5, BLOCK_HALF)
        self.assertTrue(self.exp.toppled())


class CliWiringTest(unittest.TestCase):
    def test_experiment_implies_industrial_and_real_blocks(self):
        from demo_live.__main__ import parse_args

        args = parse_args(["--experiment"])
        self.assertTrue(args.industrial)
        self.assertTrue(args.real_blocks)

    def test_experiment_and_collab_are_mutually_exclusive(self):
        from demo_live.__main__ import parse_args

        with contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            parse_args(["--experiment", "--collab"])


class RealPhysicsScheduleTest(unittest.TestCase):
    """Pin the bracketing physics the show depends on: the second offset in
    the schedule survives, the last one genuinely topples."""

    def _drop_tower(self, d: float):
        from demo_live.physics import World

        with contextlib.redirect_stdout(io.StringIO()):
            world = World(real_blocks=True)
            for _ in range(20):
                world.step()
            colors = ("workpiece", "red", "green")  # any three real bodies
            for i, c in enumerate(colors):
                b = world.find_block(c)
                world.grab_block(b)
                world.move_block(b, (2.05 - i * d, (2 * i + 1) * BLOCK_HALF + 0.005))
                world.step()
                world.release_block(b)
                for _ in range(40):
                    world.step()
            for _ in range(240):  # ~2 s settle at 1/120
                world.step()
        return [world.find_block(c) for c in colors]

    def test_mid_schedule_offset_is_stable(self):
        blocks = self._drop_tower(OFFSET_SCHEDULE[1])
        self.assertTrue(all(abs(b.angle) < TOPPLE_ANGLE_RAD for b in blocks),
                        f"4 cm/layer must survive; angles={[b.angle for b in blocks]}")
        self.assertGreater(blocks[-1].xz[1], 3 * BLOCK_HALF,
                           "top block should still be at stacked height")

    def _toppled(self, d: float) -> bool:
        blocks = self._drop_tower(d)
        return (any(abs(b.angle) > TOPPLE_ANGLE_RAD for b in blocks)
                or blocks[-1].xz[1] < 3 * BLOCK_HALF)

    def test_final_schedule_offset_topples_and_boundary_below_rigid_bound(self):
        """9 cm/layer must topple. Also pin the EMPIRICAL boundary: the
        rigid-static derivation (report §4.6) gives an ideal upper bound
        d > BLOCK_HALF/1.5 ≈ 6.67 cm, but real XPBD topples earlier (finite
        contact compliance + the release transient), so 5 cm already topples
        — the measured boundary sits in (4, 5] cm, well below 6.67. Do NOT
        assert agreement with 6.67 cm; it would fail. Regenerate if retuned."""
        self.assertTrue(self._toppled(OFFSET_SCHEDULE[-1]), "9 cm/layer must topple")
        self.assertTrue(self._toppled(0.05),
                        "5 cm/layer already topples under real XPBD — measured "
                        "boundary is below the 6.67 cm rigid bound")


if __name__ == "__main__":
    unittest.main()
