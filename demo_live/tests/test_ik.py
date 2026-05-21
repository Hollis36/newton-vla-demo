"""Unit tests for the closed-form 3-link planar IK.

Verifies FK(IK(target)) ≈ target within tolerance for reachable points,
and that unreachable points are flagged but still produce finite angles.
"""

from __future__ import annotations

import math
import unittest

from demo_live import config as C
from demo_live.ik import forward_kinematics, solve_ik
from demo_live.physics import LINK_LENGTHS, TOTAL_REACH

TOL = 1e-3   # meters — looser than machine precision, tighter than rendering


def _angle_diff(a: float, b: float) -> float:
    """Absolute angular distance in [0, π], taking 2π wraparound into account."""
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return abs(d)


class ClosedFormIKTest(unittest.TestCase):
    """Round-trip IK → FK should recover target for reachable points."""

    def _roundtrip(self, x: float, z: float, hand_angle: float = -math.pi / 2) -> None:
        sol = solve_ik(x, z, hand_angle=hand_angle)
        self.assertTrue(all(math.isfinite(q) for q in sol.q),
                        f"IK returned non-finite for ({x},{z}): {sol.q}")
        if sol.ok:
            fx, fz, fa = forward_kinematics(*sol.q)
            self.assertAlmostEqual(fx, x, delta=TOL,
                                   msg=f"x mismatch for ({x},{z})")
            self.assertAlmostEqual(fz, z, delta=TOL,
                                   msg=f"z mismatch for ({x},{z})")
            # FK accumulates without wrap, so compare modulo 2π.
            self.assertLess(_angle_diff(fa, hand_angle), TOL,
                            msg=f"hand angle mismatch for ({x},{z}): fa={fa}, ha={hand_angle}")

    def test_straight_ahead_is_reachable(self) -> None:
        """Target at (0.5, ARM_BASE_Z) pointing down is within reach."""
        self._roundtrip(0.5, C.ARM_BASE_Z)

    def test_above_base_is_reachable(self) -> None:
        """Target directly above the base, ~0.3 m up."""
        self._roundtrip(0.0, C.ARM_BASE_Z + 0.3, hand_angle=math.pi / 2)

    def test_block_pickup_pose(self) -> None:
        """Realistic pickup pose: 0.7 m forward, 0.1 m above ground."""
        self._roundtrip(0.7, 0.1)

    def test_sweep_reachable_grid(self) -> None:
        """Sweep a grid of reachable targets and confirm FK(IK(p)) ≈ p."""
        for x in (0.2, 0.4, 0.6, 0.8):
            for z in (0.2, 0.4, 0.6, 0.8):
                with self.subTest(x=x, z=z):
                    self._roundtrip(x, z)

    def test_unreachable_returns_not_ok_but_finite(self) -> None:
        """A target beyond TOTAL_REACH must flag ok=False but still finite."""
        far_x = TOTAL_REACH + 0.5
        sol = solve_ik(far_x, C.ARM_BASE_Z)
        self.assertFalse(sol.ok, "far-away target should not be reachable")
        self.assertTrue(all(math.isfinite(q) for q in sol.q),
                        "unreachable solution must still be finite for renderer safety")
        self.assertGreater(sol.reach_ratio, 1.0,
                           "reach_ratio should exceed 1 for unreachable target")

    def test_reach_ratio_matches_intuition(self) -> None:
        """Reach ratio should be < 1 for targets inside workspace."""
        sol = solve_ik(0.5, C.ARM_BASE_Z)
        self.assertTrue(sol.ok)
        self.assertLess(sol.reach_ratio, 1.0)

    def test_elbow_up_vs_down_give_same_tip(self) -> None:
        """Elbow up / elbow down both reach the same point (different shape)."""
        x, z = 0.6, C.ARM_BASE_Z
        up = solve_ik(x, z, elbow_up=True)
        down = solve_ik(x, z, elbow_up=False)
        self.assertTrue(up.ok and down.ok)
        fx_u, fz_u, _ = forward_kinematics(*up.q)
        fx_d, fz_d, _ = forward_kinematics(*down.q)
        self.assertAlmostEqual(fx_u, fx_d, delta=TOL)
        self.assertAlmostEqual(fz_u, fz_d, delta=TOL)

    def test_angles_are_wrapped(self) -> None:
        """All returned joint angles must lie in [-π, π]."""
        sol = solve_ik(0.5, C.ARM_BASE_Z)
        for q in sol.q:
            self.assertGreaterEqual(q, -math.pi - 1e-9)
            self.assertLessEqual(q, math.pi + 1e-9)


class ForwardKinematicsTest(unittest.TestCase):
    """Direct checks on forward_kinematics."""

    def test_rest_pose_fk_is_consistent(self) -> None:
        """FK at joint angles = (0, 0, 0) puts tip straight forward."""
        x, z, a = forward_kinematics(0.0, 0.0, 0.0)
        expected_x = sum(LINK_LENGTHS)
        expected_z = C.ARM_BASE_Z
        self.assertAlmostEqual(x, expected_x, delta=TOL)
        self.assertAlmostEqual(z, expected_z, delta=TOL)
        self.assertAlmostEqual(a, 0.0, delta=TOL)

    def test_straight_up_fk(self) -> None:
        """All three joints at π/2 → tip straight up."""
        x, z, a = forward_kinematics(math.pi / 2, 0.0, 0.0)
        self.assertAlmostEqual(x, 0.0, delta=TOL)
        self.assertAlmostEqual(z, C.ARM_BASE_Z + sum(LINK_LENGTHS), delta=TOL)
        self.assertLess(_angle_diff(a, math.pi / 2), TOL)


if __name__ == "__main__":
    unittest.main()
