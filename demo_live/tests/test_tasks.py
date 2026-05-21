"""Unit tests for the TaskExecutor program builders + min-jerk easing.

These tests use a minimal FakeWorld stub to avoid booting Newton/Warp
(saving ~3 s per test run). The dynamic update() loop is exercised
end-to-end in test_scripted_flows.py — here we just lock in the program
shape and the easing curve.
"""

from __future__ import annotations

import unittest

from demo_live import tasks
from demo_live.physics import BLOCK_HALF, Block


class FakeWorld:
    """Just enough of demo_live.physics.World for program builders.

    The builders only ever touch:
      - world.find_block(color)  →  Block | None
      - world.base_x             →  float (read)
      - world.base_drive_speed   →  float (read)
      - world.move_block(b, xz)  →  side-effect (we don't assert on it)
    """

    base_drive_speed = 0.8

    def __init__(self, base_x: float = 0.0) -> None:
        self.base_x = base_x
        self._blocks = {
            "red": Block(color="red", xz=(0.9, 0.1)),
            "green": Block(color="green", xz=(1.1, 0.1)),
            "blue": Block(color="blue", xz=(1.3, 0.1)),
            "yellow": Block(color="yellow", xz=(-0.9, 0.1)),
        }
        self.moves: list[tuple[str, tuple[float, float]]] = []

    def find_block(self, color: str) -> Block | None:
        return self._blocks.get(color)

    def move_block(self, block: Block, xz: tuple[float, float]) -> None:
        self.moves.append((block.color, xz))


def _make_executor(base_x: float = 0.0) -> tasks.TaskExecutor:
    """A TaskExecutor wired to FakeWorld with no real controller — safe to
    call all the program builders, unsafe to call .update() / ._start_segment()
    (they need ik.solve_ik on a real controller). The tests below stick to
    builders only."""
    return tasks.TaskExecutor(world=FakeWorld(base_x=base_x), ctrl=object())


# ============================================================================
# _ease_min_jerk
# ============================================================================


class EaseMinJerkTest(unittest.TestCase):
    """The wind-up + back-ease-out curve must start at 0, land exactly on 1.0
    at t=1, and overshoot 1.0 somewhere in the back-ease region."""

    def test_t0_is_zero(self) -> None:
        self.assertAlmostEqual(tasks._ease_min_jerk(0.0), 0.0, places=6)

    def test_t1_lands_exactly_on_one(self) -> None:
        # This is the load-bearing property: placement precision depends on it.
        self.assertAlmostEqual(tasks._ease_min_jerk(1.0), 1.0, places=6)

    def test_clamps_below_zero(self) -> None:
        self.assertAlmostEqual(tasks._ease_min_jerk(-0.5), 0.0, places=6)

    def test_clamps_above_one(self) -> None:
        self.assertAlmostEqual(tasks._ease_min_jerk(1.5), 1.0, places=6)

    def test_windup_dips_negative(self) -> None:
        # Just inside the wind-up zone the curve should be negative (reverse).
        y = tasks._ease_min_jerk(tasks.WINDUP_END * 0.5)
        self.assertLess(y, 0.0, f"expected negative wind-up; got {y}")
        # Magnitude bounded by WINDUP_DEPTH.
        self.assertGreaterEqual(y, tasks.WINDUP_DEPTH * 1.01)

    def test_overshoots_one_in_back_ease(self) -> None:
        # Back ease-out should peak above 1.0 somewhere in the second half.
        peak = max(tasks._ease_min_jerk(t) for t in (0.5, 0.6, 0.7, 0.75, 0.8, 0.85))
        self.assertGreater(peak, 1.02, f"expected overshoot > 2%; got peak={peak}")


# ============================================================================
# make_pick
# ============================================================================


class MakePickTest(unittest.TestCase):
    def test_unknown_color_returns_empty(self) -> None:
        ex = _make_executor()
        self.assertEqual(ex.make_pick("purple"), [])

    def test_pick_red_returns_drive_plus_three_arm_waypoints(self) -> None:
        ex = _make_executor()
        plan = ex.make_pick("red")
        # _ensure_reachable prepends make_drive (2 waypoints), then hover/grasp/lift.
        self.assertEqual(len(plan), 5, f"expected 5 waypoints, got {len(plan)}")
        # Last three waypoints have semantic labels.
        labels = [wp.label for wp in plan[-3:]]
        self.assertIn("Approach red", labels[0])
        self.assertIn("Descend", labels[1])
        self.assertEqual("Lift", labels[2])

    def test_grasp_waypoint_sits_above_block_center(self) -> None:
        """The grasp target Z should be block_z + EE_TO_JAW_CENTER, so the
        jaws wrap the block's sides (not slam into the top)."""
        ex = _make_executor()
        plan = ex.make_pick("red")
        red = ex.world.find_block("red")
        grasp_wp = plan[-2]  # hover, grasp, lift → grasp is second-to-last
        self.assertAlmostEqual(
            grasp_wp.target_xz[0], red.xz[0], places=4,
            msg="grasp X should align with block X",
        )
        self.assertAlmostEqual(
            grasp_wp.target_xz[1], red.xz[1] + tasks.EE_TO_JAW_CENTER, places=4,
            msg="grasp Z should be block_z + EE_TO_JAW_CENTER",
        )


# ============================================================================
# make_place
# ============================================================================


class MakePlaceTest(unittest.TestCase):
    def test_place_returns_drive_plus_three_arm_waypoints(self) -> None:
        ex = _make_executor()
        plan = ex.make_place((-0.6, 0.0))
        self.assertEqual(len(plan), 5)
        labels = [wp.label for wp in plan[-3:]]
        self.assertEqual(labels[0], "Move above target")
        self.assertIn("Descend", labels[1])
        self.assertEqual(labels[2], "Retreat")

    def test_descend_waypoint_above_target_by_jaw_offset(self) -> None:
        ex = _make_executor()
        plan = ex.make_place((-0.6, 0.0))
        descend_wp = plan[-2]
        self.assertAlmostEqual(descend_wp.target_xz[0], -0.6, places=4)
        self.assertAlmostEqual(
            descend_wp.target_xz[1], 0.0 + tasks.EE_TO_JAW_CENTER, places=4,
        )


# ============================================================================
# make_drive
# ============================================================================


class MakeDriveTest(unittest.TestCase):
    def test_drive_clamps_to_workspace_bounds(self) -> None:
        ex = _make_executor()
        plan = ex.make_drive(5.0)
        # Two waypoints (kick-off + driving). The "Drive to" label encodes
        # the clamped value.
        self.assertEqual(len(plan), 2)
        self.assertIn("+1.60", plan[0].label, plan[0].label)
        plan = ex.make_drive(-9.0)
        self.assertIn("-1.60", plan[0].label, plan[0].label)

    def test_drive_duration_scales_with_distance(self) -> None:
        # FakeWorld.base_drive_speed = 0.8 m/s; distance 1.0 m → ~2.34 s.
        ex = _make_executor(base_x=0.0)
        plan = ex.make_drive(1.0)
        long_duration = plan[1].duration  # second waypoint carries the wait
        ex2 = _make_executor(base_x=0.0)
        plan2 = ex2.make_drive(0.1)
        short_duration = plan2[1].duration
        self.assertGreater(long_duration, short_duration)
        # Minimum 0.5 s floor for short moves.
        self.assertGreaterEqual(short_duration, 0.5)


# ============================================================================
# make_stack
# ============================================================================


class MakeStackTest(unittest.TestCase):
    def test_stack_three_colors_z_increases_per_color(self) -> None:
        """Each block's place-target Z should be (2i+1) * BLOCK_HALF — the
        physical centers of a tower of touching cubes."""
        ex = _make_executor()
        plan = ex.make_stack(["red", "green", "blue"])
        # Find the "Descend + release" waypoints (one per block) — those carry
        # the actual target Z that the block will end up at.
        descend = [wp for wp in plan if wp.label == "Descend + release"]
        self.assertEqual(len(descend), 3)
        # Z monotonically increases.
        zs = [wp.target_xz[1] for wp in descend]
        self.assertLess(zs[0], zs[1])
        self.assertLess(zs[1], zs[2])
        # Each Z matches the analytical (2i+1)*BLOCK_HALF + EE_TO_JAW_CENTER offset.
        for i, wp in enumerate(descend):
            expected = (2 * i + 1) * BLOCK_HALF + tasks.EE_TO_JAW_CENTER
            self.assertAlmostEqual(wp.target_xz[1], expected, places=4)

    def test_stack_targets_centered_at_stack_x(self) -> None:
        ex = _make_executor()
        plan = ex.make_stack(["red", "green", "blue"])
        descend = [wp for wp in plan if wp.label == "Descend + release"]
        for wp in descend:
            self.assertAlmostEqual(wp.target_xz[0], tasks.STACK_X, places=4)

    def test_stack_returns_to_home_between_blocks(self) -> None:
        ex = _make_executor()
        plan = ex.make_stack(["red", "green", "blue"])
        returns = [wp for wp in plan if wp.label == "Return"]
        self.assertEqual(len(returns), 3, "one Return waypoint after each block")


# ============================================================================
# Fixed-arm guard (Arm B) — _ensure_reachable must NOT drive the world base
# ============================================================================


class FixedArmReachabilityTest(unittest.TestCase):
    """Arm B (fixed pedestal, `anchor_world_x` set) cannot drive — and
    `make_drive` would mutate Arm A's base mid-task. Verify the early-out
    in `_ensure_reachable` so this regression can't slip back in.

    The mirror test in `test_scripted_constants.py::ArmBIdleCycleTest`
    asserts the end-to-end invariant (no `drive_to` leaks from the Arm B
    idle shuttle); this one isolates the unit-level guard."""

    def test_fixed_arm_pick_emits_no_drive_waypoint(self) -> None:
        ex = _make_executor()
        ex.anchor_world_x = lambda: 2.40       # mark as fixed (Arm B style)
        plan = ex.make_pick("red")
        # Mobile arm would emit 5 waypoints (2 drive + 3 pick); fixed arm
        # should emit only the 3 hover/grasp/lift waypoints.
        self.assertEqual(len(plan), 3, f"unexpected fixed-arm plan: {plan}")
        for wp in plan:
            self.assertNotIn("Drive", wp.label,
                              f"fixed arm should not emit drive waypoint: {wp.label!r}")

    def test_mobile_arm_pick_still_emits_drive(self) -> None:
        """Regression: the fix must not break the mobile Arm A code path."""
        ex = _make_executor()
        plan = ex.make_pick("red")
        self.assertGreaterEqual(len(plan), 5, f"mobile plan should include drive: {plan}")
        self.assertTrue(any("Drive" in wp.label for wp in plan),
                        "mobile arm should still emit a drive waypoint")


# ============================================================================
# Gestures (wave / point / bow / dance) — decorative, no IK constraints
# ============================================================================


class GesturesTest(unittest.TestCase):
    """Each gesture should produce a non-empty waypoint program that starts
    away from rest, exercises some range of motion, and returns to the
    GESTURE_HOME pose so the demo doesn't strand the arm mid-air."""

    def test_wave_returns_to_home(self) -> None:
        ex = _make_executor()
        plan = ex.make_wave(sweeps=2)
        self.assertGreaterEqual(len(plan), 4)  # up + 2*2 sweeps + home
        self.assertEqual(plan[-1].target_xz, tasks.TaskExecutor.GESTURE_HOME)

    def test_wave_sweeps_alternate_x(self) -> None:
        """Left + right sweep waypoints should straddle the home x (0.7)."""
        ex = _make_executor()
        plan = ex.make_wave(sweeps=1)
        sweeps = [wp for wp in plan if wp.label.startswith("Wave left")
                                       or wp.label.startswith("Wave right")]
        self.assertEqual(len(sweeps), 2)
        xs = [wp.target_xz[0] for wp in sweeps]
        self.assertLess(min(xs), 0.7)
        self.assertGreater(max(xs), 0.7)

    def test_point_left_lands_left_of_home(self) -> None:
        ex = _make_executor()
        plan = ex.make_point("left")
        self.assertGreaterEqual(len(plan), 3)
        # The first (extend) waypoint should be left of home.
        self.assertLess(plan[0].target_xz[0], 0.7)
        # The last waypoint returns to home.
        self.assertEqual(plan[-1].target_xz, tasks.TaskExecutor.GESTURE_HOME)

    def test_point_right_lands_right_of_home(self) -> None:
        ex = _make_executor()
        plan = ex.make_point("right")
        self.assertGreater(plan[0].target_xz[0], 0.7)

    def test_point_unknown_direction_collapses_to_left(self) -> None:
        ex = _make_executor()
        plan = ex.make_point("northwest")     # not a known label
        self.assertLess(plan[0].target_xz[0], 0.7)

    def test_bow_dips_below_home(self) -> None:
        ex = _make_executor()
        plan = ex.make_bow(depth=0.35)
        # The first / "Bowing" waypoint should be below home.
        bow_wp = plan[0]
        self.assertLess(bow_wp.target_xz[1],
                        tasks.TaskExecutor.GESTURE_HOME[1])
        # And we rise back to home.
        self.assertEqual(plan[-1].target_xz, tasks.TaskExecutor.GESTURE_HOME)

    def test_bow_depth_clamped(self) -> None:
        ex = _make_executor()
        # depth=10 (silly) should still produce a sane bow that doesn't go
        # below z=0 (the ground).
        plan = ex.make_bow(depth=10)
        self.assertGreater(plan[0].target_xz[1], 0.0)

    def test_dance_n_beats_plus_return(self) -> None:
        ex = _make_executor()
        plan = ex.make_dance(beats=4)
        self.assertEqual(len(plan), 5)        # 4 beats + return
        self.assertEqual(plan[-1].target_xz, tasks.TaskExecutor.GESTURE_HOME)

    def test_dance_floor_two_beats(self) -> None:
        """beats <= 1 should not produce a degenerate single-pose dance."""
        ex = _make_executor()
        plan = ex.make_dance(beats=1)
        # Floor of 2 beats + return waypoint.
        self.assertGreaterEqual(len(plan), 3)


if __name__ == "__main__":
    unittest.main()
