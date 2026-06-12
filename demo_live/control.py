"""Joint-space controller that smoothly drives the arm to target angles.

The Newton XPBD solver applies PD to each joint given `model.joint_target`.
We slew the target each frame so motion looks smooth and "robotic," not
teleported. The low-pass filter also prevents the arm from fighting its own
inertia when a big target change arrives.
"""

from __future__ import annotations

import math
import time

import numpy as np
import warp as wp

from .physics import REST_POSE, FKArmRig, World

# Per-joint amplitudes for the idle wobble (radians). Wrist allowed to move
# more than the elbow than the shoulder — small lower in the chain so the
# accumulated EE motion stays sub-cm.
_IDLE_AMPL = np.array([0.012, 0.018, 0.024], dtype=np.float32)
# Per-joint frequencies (Hz). Mutually-prime values so the pose never
# repeats — the arm "breathes" without looking metronomic.
_IDLE_FREQ = np.array([0.21, 0.29, 0.37], dtype=np.float32)
# Per-joint phase offsets (radians). Just three irrational-ish numbers.
_IDLE_PHASE = np.array([0.0, 1.7, 3.2], dtype=np.float32)


class JointController:
    """Slew-rate-limited target tracker for the 3-DOF arm."""

    def __init__(
        self,
        world: World,
        max_rate: float = 14.0,      # rad/s per joint (tuned for grace over speed)
        smooth: float = 0.16,        # 1st-order filter alpha (0..1, higher = snappier)
    ) -> None:
        self.world = world
        self.max_rate = max_rate
        self.smooth = smooth
        self.current_target = np.array(REST_POSE, dtype=np.float32)
        self.desired = np.array(REST_POSE, dtype=np.float32)
        self._apply_to_model()

    # ---------------------------------------------------------- setters

    def set_target(self, q: tuple[float, float, float]) -> None:
        """Set the **final** desired joint angles. Slewing happens in update().

        Rejects any target that contains NaN/inf — IK sometimes produces those
        when a caller hands in an unreachable point, and feeding NaN into the
        XPBD solver corrupts the state permanently.
        """
        arr = np.array(q, dtype=np.float32)
        if not np.all(np.isfinite(arr)):
            return
        self.desired = arr

    def go_home(self) -> None:
        self.set_target(REST_POSE)

    def snap_to(self, q: tuple[float, float, float]) -> None:
        """Force BOTH current_target and desired to `q`, bypassing the slew
        filter. Used by the task executor at waypoint completion so the
        rendered arm matches the commanded pose exactly — otherwise 22%
        filter residuals leak into the visible block-placement position."""
        arr = np.array(q, dtype=np.float32)
        if not np.all(np.isfinite(arr)):
            return
        self.current_target = arr.copy()
        self.desired = arr.copy()
        self._apply_to_model()

    # ---------------------------------------------------------- per-frame

    def update(self, dt: float) -> None:
        """Low-pass filter current_target toward desired, clamped by max_rate.

        When `desired` is REST_POSE and the arm has settled there, an idle
        wobble (sub-degree, multi-frequency sine) is added on top so the
        robot looks like it's breathing rather than frozen between tasks.
        """
        # 1st-order filter
        filtered = self.current_target + self.smooth * (self.desired - self.current_target)
        # rate clamp
        delta = filtered - self.current_target
        max_step = self.max_rate * dt
        delta = np.clip(delta, -max_step, max_step)
        self.current_target = self.current_target + delta

        # Idle wobble — only at rest, only after the slew has settled.
        rest = np.array(REST_POSE, dtype=np.float32)
        at_rest = bool(np.allclose(self.desired, rest, atol=0.02))
        settled = bool(np.linalg.norm(self.current_target - rest) < 0.04)
        if at_rest and settled:
            t = time.perf_counter()
            wobble = _IDLE_AMPL * np.sin(2 * math.pi * _IDLE_FREQ * t + _IDLE_PHASE)
            self._apply_to_model(extra=wobble)
        else:
            self._apply_to_model()

    # ---------------------------------------------------------- internal

    def _apply_to_model(self, extra: np.ndarray | None = None) -> None:
        """Push current_target (+ optional `extra` per-joint offset) into the
        solver's PD target buffer. `extra` is used by the idle wobble path."""
        ctrl = self.world.control
        if ctrl.joint_target_pos is None:
            model_tgt = self.world.model.joint_target_pos
            if model_tgt is not None:
                ctrl.joint_target_pos = model_tgt.clone()
            else:
                ctrl.joint_target_pos = wp.zeros(
                    self.world.model.joint_dof_count, dtype=wp.float32
                )
        tgt = ctrl.joint_target_pos.numpy().copy()
        if extra is not None:
            tgt[:3] = self.current_target + extra
        else:
            tgt[:3] = self.current_target
        ctrl.joint_target_pos.assign(tgt)

    # ---------------------------------------------------------- observers

    @property
    def tracking_error(self) -> float:
        return float(np.linalg.norm(self.current_target - self.desired))

    @property
    def settled(self) -> bool:
        """True when current and desired are close enough (for step chaining)."""
        return self.tracking_error < 0.05 and self._joint_velocity() < 0.3

    def _joint_velocity(self) -> float:
        qd = self.world.model.joint_qd.numpy()[:3]
        return float(np.linalg.norm(qd))


# ---------------------------------------------------------------------------
# FKJointController — the same slew/smooth/wobble interface, but for an arm
# rig that has no Newton physics behind it (the secondary "Arm B" in the
# multi-arm demo). The rig stores joint angles in plain Python; we just
# update its `joint_target` attribute each frame.
# ---------------------------------------------------------------------------

class FKJointController:
    """Render-only joint controller for an FKArmRig.

    Mirrors `JointController`'s public surface (set_target, go_home, snap_to,
    update, settled, tracking_error) so `TaskExecutor` and the rest of the
    pipeline don't care which kind of arm they're driving.
    """

    def __init__(
        self,
        rig: FKArmRig,
        max_rate: float = 14.0,
        smooth: float = 0.16,
    ) -> None:
        self.rig = rig
        self.max_rate = max_rate
        self.smooth = smooth
        self.current_target = np.array(REST_POSE, dtype=np.float32)
        self.desired = np.array(REST_POSE, dtype=np.float32)
        self._apply_to_rig()

    def set_target(self, q: tuple[float, float, float]) -> None:
        arr = np.array(q, dtype=np.float32)
        if not np.all(np.isfinite(arr)):
            return
        self.desired = arr

    def go_home(self) -> None:
        self.set_target(REST_POSE)

    def snap_to(self, q: tuple[float, float, float]) -> None:
        arr = np.array(q, dtype=np.float32)
        if not np.all(np.isfinite(arr)):
            return
        self.current_target = arr.copy()
        self.desired = arr.copy()
        self._apply_to_rig()

    def update(self, dt: float) -> None:
        filtered = self.current_target + self.smooth * (self.desired - self.current_target)
        delta = filtered - self.current_target
        max_step = self.max_rate * dt
        delta = np.clip(delta, -max_step, max_step)
        self.current_target = self.current_target + delta

        rest = np.array(REST_POSE, dtype=np.float32)
        at_rest = bool(np.allclose(self.desired, rest, atol=0.02))
        settled = bool(np.linalg.norm(self.current_target - rest) < 0.04)
        if at_rest and settled:
            t = time.perf_counter()
            wobble = _IDLE_AMPL * np.sin(2 * math.pi * _IDLE_FREQ * t + _IDLE_PHASE)
            self._apply_to_rig(extra=wobble)
        else:
            self._apply_to_rig()

    def _apply_to_rig(self, extra: np.ndarray | None = None) -> None:
        if extra is not None:
            self.rig.joint_target = (self.current_target + extra).astype(np.float32)
        else:
            self.rig.joint_target = self.current_target.astype(np.float32).copy()

    @property
    def tracking_error(self) -> float:
        return float(np.linalg.norm(self.current_target - self.desired))

    @property
    def settled(self) -> bool:
        return self.tracking_error < 0.05
