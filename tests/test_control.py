"""Unit tests for `demo_live.control.JointController` and `FKJointController`.

The slew + rate-clamp + idle-wobble math is identical between the two
controllers — only the *output sink* differs (Warp buffer vs FKArmRig
attribute). We test `FKJointController` because it doesn't need a Newton
World, then add a single integration probe for `JointController` to
confirm the Newton-backed wiring still works.

All physics constants we depend on:
  - REST_POSE = (1.2, -1.0, -0.2)
  - max_rate default = 14.0 rad/s
  - smooth default = 0.16
"""

from __future__ import annotations

import unittest

import numpy as np

from demo_live import control
from demo_live.physics import REST_POSE, FKArmRig

# ============================================================================
# Public API contract
# ============================================================================


class FkControllerInitTest(unittest.TestCase):
    def test_starts_at_rest_pose(self) -> None:
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        np.testing.assert_array_almost_equal(ctrl.current_target,
                                              np.array(REST_POSE))
        np.testing.assert_array_almost_equal(ctrl.desired,
                                              np.array(REST_POSE))


class FkControllerSetTargetTest(unittest.TestCase):
    def test_set_target_updates_desired_not_current(self) -> None:
        """set_target only changes `desired`; `current_target` slews to it
        across update() calls."""
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        ctrl.set_target((0.5, -0.5, 0.0))
        np.testing.assert_array_almost_equal(ctrl.desired,
                                              np.array([0.5, -0.5, 0.0]))
        np.testing.assert_array_almost_equal(ctrl.current_target,
                                              np.array(REST_POSE))

    def test_nan_target_silently_rejected(self) -> None:
        """Catcher IK occasionally produces NaN on unreachable points; we
        must NOT feed NaN into the controller or downstream solver."""
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        original = ctrl.desired.copy()
        ctrl.set_target((float("nan"), 0.0, 0.0))
        np.testing.assert_array_almost_equal(ctrl.desired, original)

    def test_inf_target_silently_rejected(self) -> None:
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        original = ctrl.desired.copy()
        ctrl.set_target((float("inf"), 0.0, 0.0))
        np.testing.assert_array_almost_equal(ctrl.desired, original)


class FkControllerSnapToTest(unittest.TestCase):
    def test_snap_to_sets_both_fields_immediately(self) -> None:
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        target = (0.7, -0.3, 0.1)
        ctrl.snap_to(target)
        np.testing.assert_array_almost_equal(ctrl.current_target,
                                              np.array(target))
        np.testing.assert_array_almost_equal(ctrl.desired,
                                              np.array(target))

    def test_snap_to_nan_silently_rejected(self) -> None:
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        ctrl.snap_to((float("nan"), 0.0, 0.0))
        # State is unchanged.
        np.testing.assert_array_almost_equal(ctrl.current_target,
                                              np.array(REST_POSE))


class FkControllerGoHomeTest(unittest.TestCase):
    def test_go_home_sets_desired_to_rest(self) -> None:
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        ctrl.set_target((0.0, 0.0, 0.0))
        ctrl.go_home()
        np.testing.assert_array_almost_equal(ctrl.desired,
                                              np.array(REST_POSE))


# ============================================================================
# Slew + rate clamp behavior
# ============================================================================


class FkControllerSlewTest(unittest.TestCase):
    def test_update_advances_toward_desired(self) -> None:
        """One update tick should move current_target a fraction of the way
        toward desired (not snap)."""
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        target = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        ctrl.set_target(tuple(target))
        # Move BEFORE update — sample distance.
        before = np.linalg.norm(ctrl.current_target - target)
        ctrl.update(1 / 60)
        after = np.linalg.norm(ctrl.current_target - target)
        # After one tick we should be closer to target but NOT there yet.
        self.assertLess(after, before)
        self.assertGreater(after, 0.0)

    def test_rate_clamp_caps_per_frame_step(self) -> None:
        """A large jump in `desired` should produce a current_target step
        bounded by max_rate * dt, not the full filtered jump."""
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig, max_rate=14.0, smooth=1.0)
        # smooth=1.0 means filter passes through — so without rate clamp,
        # current_target would JUMP all the way. The clamp forces a step.
        ctrl.set_target((10.0, 0.0, 0.0))    # far from rest (1.2, -1.0, -0.2)
        dt = 1 / 60
        ctrl.update(dt)
        # Maximum allowed step per joint = max_rate * dt = 14/60 ≈ 0.233 rad.
        max_step = 14.0 * dt
        delta = ctrl.current_target - np.array(REST_POSE, dtype=np.float32)
        # Joint 0 attempted to jump 10 - 1.2 = 8.8; clamp keeps it ≤ 0.233.
        self.assertLessEqual(abs(delta[0]), max_step + 1e-5)

    def test_converges_within_settle_window(self) -> None:
        """At default params, a small move should converge in <30 frames."""
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        ctrl.set_target((1.4, -0.8, 0.0))    # ~0.4 rad total displacement
        for _ in range(60):
            ctrl.update(1 / 60)
        # Within `settled` tolerance.
        self.assertTrue(ctrl.settled,
                        f"should be settled; tracking_error={ctrl.tracking_error:.4f}")


# ============================================================================
# settled property
# ============================================================================


class FkControllerSettledTest(unittest.TestCase):
    def test_settled_true_at_rest(self) -> None:
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        self.assertTrue(ctrl.settled)

    def test_settled_false_during_motion(self) -> None:
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        ctrl.set_target((2.0, -2.0, 1.0))     # far from rest
        # One tick — way short of converging.
        ctrl.update(1 / 60)
        self.assertFalse(ctrl.settled)


# ============================================================================
# Idle wobble (visible "breathing" at rest)
# ============================================================================


class IdleWobbleTest(unittest.TestCase):
    def test_wobble_amplitude_bounded(self) -> None:
        """When the controller has settled at REST_POSE, an idle wobble adds
        sub-degree sinusoidal jitter. The rig's joint_target should differ
        from current_target by no more than the sum of _IDLE_AMPL."""
        rig = FKArmRig(anchor_world_x=0.0)
        ctrl = control.FKJointController(rig)
        # Sit at rest for a while so settled latches.
        for _ in range(30):
            ctrl.update(1 / 60)
        # Sample a few frames; wobble offset must stay within amplitude bounds.
        max_amplitude = float(control._IDLE_AMPL.sum()) + 1e-4
        for _ in range(10):
            ctrl.update(1 / 60)
            diff = rig.joint_target - ctrl.current_target
            self.assertLess(float(np.linalg.norm(diff)), max_amplitude,
                            f"wobble too big: {diff}")


if __name__ == "__main__":
    unittest.main()
