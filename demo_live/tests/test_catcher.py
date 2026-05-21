"""Unit tests for `demo_live.catcher` — the MPC-style ball intercept.

`BallCatcher._predict` is closed-form: it solves z(t) = INTERCEPT_Z under
constant gravity with z₀ + v_z·t − ½ g t² = INTERCEPT_Z. The whole point
of the demo's "classical control" beat is that this resolves analytically,
so the math is worth pinning down with unit tests.

A FakeWorld + StubController stand in for the Newton-backed world so the
tests run in milliseconds (no Warp boot).
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr

from demo_live import catcher


class FakeArmState:
    """Just the `end_effector` attribute that catcher.update reads."""

    def __init__(self, ee_xz: tuple[float, float] = (0.7, 1.0)) -> None:
        self.end_effector = ee_xz


class FakeWorld:
    """Just enough of physics.World for catcher's read/write surface."""

    def __init__(self) -> None:
        self.base_x: float = 0.0
        self.base_target_x: float = 0.0
        self._ball_pos: tuple[float, float] = (1.5, 0.7)
        self._ball_vel: tuple[float, float] = (-1.8, 3.4)
        self._ball_active: bool = False
        self.drive_calls: list[float] = []
        self.launch_calls: list[tuple[tuple[float, float], tuple[float, float]]] = []
        self.park_called: int = 0
        self._arm_state = FakeArmState()

    def ball_state(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return self._ball_pos, self._ball_vel

    def set_ball(self, pos: tuple[float, float], vel: tuple[float, float],
                 active: bool = True) -> None:
        """Test helper: override the ball state outside the launch path."""
        self._ball_pos = pos
        self._ball_vel = vel
        self._ball_active = active

    def launch_ball(self, start_xz: tuple[float, float],
                    velocity_xz: tuple[float, float]) -> None:
        self._ball_pos = (float(start_xz[0]), float(start_xz[1]))
        self._ball_vel = (float(velocity_xz[0]), float(velocity_xz[1]))
        self._ball_active = True
        self.launch_calls.append((start_xz, velocity_xz))

    def park_ball(self) -> None:
        self._ball_pos = (10.0, 5.0)
        self._ball_vel = (0.0, 0.0)
        self._ball_active = False
        self.park_called += 1

    def drive_to(self, target_x: float) -> None:
        self.drive_calls.append(target_x)
        self.base_target_x = float(target_x)

    def arm_state_from_target(self) -> FakeArmState:
        return self._arm_state


class StubController:
    """Just .settled, .set_target, .go_home — catcher's whole controller surface."""

    def __init__(self, settled: bool = True) -> None:
        self.settled = settled
        self.set_target_calls: list[tuple[float, ...]] = []
        self.go_home_calls: int = 0

    def set_target(self, q) -> None:
        self.set_target_calls.append(tuple(float(v) for v in q))

    def go_home(self) -> None:
        self.go_home_calls += 1


def _make_catcher(rng_seed: int = 0) -> tuple[catcher.BallCatcher, FakeWorld, StubController]:
    w = FakeWorld()
    c = StubController()
    bc = catcher.BallCatcher(w, c, rng_seed=rng_seed)
    return bc, w, c


# ============================================================================
# Prediction._predict — closed-form ballistic intercept math
# ============================================================================


class PredictionTest(unittest.TestCase):
    def test_lobbed_ball_reaches_intercept(self) -> None:
        """A ball thrown up should cross INTERCEPT_Z and `_predict` returns
        the downward crossing with positive time-to-intercept."""
        bc, w, _ = _make_catcher()
        # Ball at z=0.7 moving up at 3.4 m/s — clears INTERCEPT_Z (1.4) easily.
        w.set_ball((1.5, 0.7), (-1.8, 3.4))
        pred = bc._predict()
        self.assertTrue(pred.ok)
        self.assertGreater(pred.time_to_intercept, 0.0)
        self.assertAlmostEqual(pred.intercept_xz[1], catcher.INTERCEPT_Z, places=4)

    def test_intercept_x_consistent_with_trajectory(self) -> None:
        """intercept_xz[0] should be x₀ + vx · t_intercept (no acceleration in x)."""
        bc, w, _ = _make_catcher()
        w.set_ball((1.5, 0.7), (-1.8, 3.4))
        pred = bc._predict()
        expected_x = 1.5 + (-1.8) * pred.time_to_intercept
        self.assertAlmostEqual(pred.intercept_xz[0], expected_x, places=4)

    def test_falling_ball_below_intercept_disc_negative(self) -> None:
        """A ball already below INTERCEPT_Z falling DOWN can never reach it
        on the way up. Disc < 0 → ok=False."""
        bc, w, _ = _make_catcher()
        # Below INTERCEPT_Z (=1.4), moving down: disc must be < 0.
        w.set_ball((0.5, 0.5), (0.0, -2.0))
        with redirect_stderr(io.StringIO()):
            pred = bc._predict()
        self.assertFalse(pred.ok)

    def test_arrival_after_window_is_rejected(self) -> None:
        """If the downward crossing is > 2.5 s away (out of valid window),
        the prediction should reject it as out-of-reach.

        Math: z(t) = z₀ - ½ g t² with vz=0; solving for INTERCEPT_Z ≈ 1.4 with
        z₀ = 50 yields t ≈ √((50 - 1.4)/4.905) ≈ 3.15 s, past the 2.5 s cap.
        """
        bc, w, _ = _make_catcher()
        w.set_ball((1.5, 50.0), (0.0, 0.0))
        pred = bc._predict()
        self.assertFalse(pred.ok)

    def test_arrival_immediately_is_rejected(self) -> None:
        """If t < 0.02 s, the ball is essentially already at INTERCEPT_Z and
        there's no time to act — should reject."""
        bc, w, _ = _make_catcher()
        # Ball exactly at INTERCEPT_Z, no vertical motion — both roots near 0.
        w.set_ball((1.5, catcher.INTERCEPT_Z), (0.0, 0.01))
        pred = bc._predict()
        self.assertFalse(pred.ok)

    def test_downward_crossing_chosen_over_upward(self) -> None:
        """Two positive roots = ball passes through INTERCEPT_Z TWICE (going
        up, then coming down). We always want the SECOND (downward) one."""
        bc, w, _ = _make_catcher()
        # Tall lob: clearly two crossings.
        w.set_ball((1.5, 0.4), (0.0, 5.0))
        pred = bc._predict()
        self.assertTrue(pred.ok)
        # Verify: at returned time, vz should be NEGATIVE (downward).
        vz_at_intercept = 5.0 - catcher.GRAVITY * pred.time_to_intercept
        self.assertLess(vz_at_intercept, 0.0,
                        "should pick the descending crossing, not the ascending one")

    def test_disc_warning_fires_once_per_pitch(self) -> None:
        """The 'no intercept' stderr warning should fire at most ONCE between
        ball launches (otherwise stderr spams the demo terminal)."""
        bc, w, _ = _make_catcher()
        # Below INTERCEPT_Z, no upward velocity → triggers the warning.
        w.set_ball((0.5, 0.5), (0.0, -2.0))
        buf = io.StringIO()
        with redirect_stderr(buf):
            bc._predict()
            bc._predict()
            bc._predict()
        n_warnings = buf.getvalue().count("[catcher] no intercept")
        self.assertEqual(n_warnings, 1,
                         f"expected 1 warning per pitch; got {n_warnings}")


# ============================================================================
# BallCatcher state machine — lifecycle (start / stop / external_launch)
# ============================================================================


class StateMachineTest(unittest.TestCase):
    def test_starts_in_idle(self) -> None:
        bc, _, _ = _make_catcher()
        self.assertEqual(bc.state, catcher.BallCatcher.STATE_IDLE)
        self.assertEqual(bc.catch_count, 0)
        self.assertEqual(bc.attempt_count, 0)

    def test_start_transitions_to_arming(self) -> None:
        bc, _, ctrl = _make_catcher()
        bc.start()
        self.assertEqual(bc.state, catcher.BallCatcher.STATE_ARMING)
        self.assertEqual(len(ctrl.set_target_calls), 1)        # ready-stance set

    def test_start_manual_sets_flag(self) -> None:
        bc, _, _ = _make_catcher()
        self.assertFalse(bc.manual)
        bc.start(manual=True)
        self.assertTrue(bc.manual)

    def test_stop_returns_to_idle_and_parks_ball(self) -> None:
        bc, world, ctrl = _make_catcher()
        bc.start()
        bc.stop()
        self.assertEqual(bc.state, catcher.BallCatcher.STATE_IDLE)
        self.assertEqual(world.park_called, 1)
        self.assertEqual(ctrl.go_home_calls, 1)


class ExternalLaunchTest(unittest.TestCase):
    def test_external_launch_ignored_when_not_manual(self) -> None:
        bc, world, _ = _make_catcher()
        bc.start(manual=False)
        bc.external_launch((1.5, 0.7), (-1.8, 3.4))
        # Non-manual: ignored, no launch.
        self.assertEqual(world.launch_calls, [])
        self.assertEqual(bc.attempt_count, 0)

    def test_external_launch_ignored_when_not_armed(self) -> None:
        bc, world, _ = _make_catcher()
        # State stays in IDLE; manual=False also doesn't matter — wrong state.
        bc.manual = True
        bc.external_launch((1.5, 0.7), (-1.8, 3.4))
        self.assertEqual(world.launch_calls, [])
        self.assertEqual(bc.attempt_count, 0)

    def test_external_launch_arming_to_tracking(self) -> None:
        bc, world, _ = _make_catcher()
        bc.start(manual=True)
        self.assertEqual(bc.state, catcher.BallCatcher.STATE_ARMING)
        bc.external_launch((1.5, 0.7), (-1.8, 3.4))
        self.assertEqual(bc.state, catcher.BallCatcher.STATE_TRACK)
        self.assertEqual(bc.attempt_count, 1)
        self.assertEqual(len(world.launch_calls), 1)

    def test_external_launch_resets_warning_flag(self) -> None:
        """Each pitch gets its own warning budget — _warned_unreachable must
        reset on launch so a new bad throw can warn again."""
        bc, _, _ = _make_catcher()
        bc.start(manual=True)
        bc._warned_unreachable = True
        bc.external_launch((1.5, 0.7), (-1.8, 3.4))
        self.assertFalse(bc._warned_unreachable)


class LaunchNewBallTest(unittest.TestCase):
    """The auto-launcher (non-manual) uses RNG for variety, so we exercise
    the state mutation rather than specific positions."""

    def test_auto_launch_increments_attempt_count(self) -> None:
        bc, world, _ = _make_catcher(rng_seed=42)
        bc._launch_new_ball()
        self.assertEqual(bc.attempt_count, 1)
        self.assertEqual(len(world.launch_calls), 1)

    def test_auto_launch_resets_warning_flag(self) -> None:
        bc, _, _ = _make_catcher(rng_seed=42)
        bc._warned_unreachable = True
        bc._launch_new_ball()
        self.assertFalse(bc._warned_unreachable)

    def test_auto_launch_position_in_expected_range(self) -> None:
        """The launcher samples x ∈ [1.3, 1.7] and z ∈ [0.4, 0.7] — verify
        the bounds across a few seeds so a refactor that swaps the ranges
        gets caught."""
        for seed in range(10):
            bc, world, _ = _make_catcher(rng_seed=seed)
            bc._launch_new_ball()
            start_xz, vel_xz = world.launch_calls[0]
            self.assertGreaterEqual(start_xz[0], 1.3)
            self.assertLessEqual(start_xz[0], 1.7)
            self.assertGreaterEqual(start_xz[1], 0.4)
            self.assertLessEqual(start_xz[1], 0.7)
            # Velocity: vx ∈ [-1.6, -1.1] (rightward → leftward),
            # vz ∈ [3.2, 4.0] (upward lob).
            self.assertLess(vel_xz[0], 0.0)
            self.assertGreater(vel_xz[1], 0.0)


if __name__ == "__main__":
    unittest.main()
