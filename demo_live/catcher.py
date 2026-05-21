"""MPC-style ball catcher: predict where the ball will enter the arm's reachable
envelope, then solve IK for an intercept pose and stream it to the controller.

"MPC" here is lightweight: we re-fit the ballistic trajectory every frame
from the current (x, z, vx, vz) observation and project forward. No
optimization solver needed — the model is closed-form.
"""

from __future__ import annotations

import math
import random
import sys
import time
from dataclasses import dataclass

from . import config as C
from . import ik
from .control import JointController
from .physics import World

GRAVITY = 9.81                          # m/s² downward
INTERCEPT_Z = C.ARM_BASE_Z + 0.40       # world-Z height where we try to catch
INTERCEPT_X_MAX = 0.95                  # reachable x with hand pointing up


@dataclass
class Prediction:
    ok: bool
    intercept_xz: tuple[float, float]
    time_to_intercept: float     # seconds


class BallCatcher:
    """State machine: idle → launch → track → reset → repeat."""

    STATE_IDLE = "idle"
    STATE_ARMING = "arming"      # arm going to pre-catch stance
    STATE_TRACK = "tracking"     # live MPC
    STATE_COOLDOWN = "cooldown"  # after catch or miss, short pause

    def __init__(
        self,
        world: World,
        controller: JointController,
        rng_seed: int | None = None,
    ) -> None:
        self.world = world
        self.ctrl = controller
        self.rng = random.Random(rng_seed)
        self.state = self.STATE_IDLE
        self.state_entered_at = time.perf_counter()
        self.last_prediction: Prediction | None = None
        self.committed_target: tuple[float, float] | None = None
        self.min_dist_this_pitch = 1e9
        self.catch_count = 0
        self.attempt_count = 0
        # Manual mode: if True, don't auto-launch a new ball after arming;
        # wait for `external_launch(...)` from the mouse drag handler.
        self.manual: bool = False
        # One-shot warning per pitch when the ballistic discriminant is
        # negative (ball never reaches INTERCEPT_Z). Reset on each launch.
        self._warned_unreachable: bool = False

    # ---------------------------------------------------------- lifecycle

    def start(self, manual: bool = False) -> None:
        self.manual = manual
        self._set_state(self.STATE_ARMING)
        # Raise arm to a "ready to catch" stance.
        self.ctrl.set_target((0.7, -0.4, -0.3))

    def stop(self) -> None:
        self.world.park_ball()
        self.ctrl.go_home()
        self._set_state(self.STATE_IDLE)

    def external_launch(
        self,
        start_xz: tuple[float, float],
        velocity_xz: tuple[float, float],
    ) -> None:
        """Manual-mode entry: audience chose where + how fast to throw."""
        if not self.manual or self.state not in (self.STATE_ARMING, self.STATE_COOLDOWN):
            return
        self.attempt_count += 1
        self.world.launch_ball(start_xz, velocity_xz)
        self.committed_target = None
        self.min_dist_this_pitch = 1e9
        self._warned_unreachable = False
        self._set_state(self.STATE_TRACK)

    # ---------------------------------------------------------- frame

    def update(self, dt: float) -> str:
        """Advance state machine. Returns status line for the UI."""
        now = time.perf_counter()
        elapsed = now - self.state_entered_at

        if self.state == self.STATE_IDLE:
            return "Ball-catch idle. Press 1 to play again."

        if self.state == self.STATE_ARMING:
            if self.manual:
                return "Ready — click and drag to throw."
            if self.ctrl.settled or elapsed > 1.2:
                self._launch_new_ball()
                self.committed_target = None
                self._set_state(self.STATE_TRACK)
            return "Arming…"

        if self.state == self.STATE_TRACK:
            pred = self._predict()
            self.last_prediction = pred

            # --- Mobile catching --------------------------------------
            # Nudge the base toward the predicted landing x — but only while
            # we haven't committed yet. Once the arm's IK target is locked in,
            # the base must hold still or the ball will miss the jaws.
            if pred.ok and self.committed_target is None:
                drive_target = max(-1.6, min(1.6, pred.intercept_xz[0]))
                # Ignore tiny corrections to avoid min-jerk restarts.
                if abs(drive_target - self.world.base_target_x) > 0.08:
                    self.world.drive_to(drive_target)

            # --- Commit once reachable --------------------------------
            base_x = self.world.base_x
            # Consider the target reachable if the ball's predicted (world) x
            # is close enough to our CURRENT base x AND the base is mostly
            # done driving (so the IK target doesn't become stale as we move).
            base_settled = abs(self.world.base_target_x - base_x) < 0.05
            if (
                pred.ok
                and self.committed_target is None
                and base_settled
                and abs(pred.intercept_xz[0] - base_x) <= 0.9
            ):
                local_x = pred.intercept_xz[0] - base_x
                local_z = pred.intercept_xz[1]

                (bx0, bz0), (vx0, vz0) = self.world.ball_state()
                t_int = pred.time_to_intercept
                vx_t = vx0
                vz_t = vz0 - GRAVITY * t_int
                raw = math.atan2(-vz_t, -vx_t)
                hand_angle = max(math.radians(35), min(math.radians(145), raw))

                sol = ik.solve_ik(
                    local_x, local_z,
                    hand_angle=hand_angle,
                    elbow_up=True,
                )
                # Only commit if IK actually reached the target AND all angles
                # are finite. Otherwise keep driving until we're in range.
                import numpy as _np
                if sol.ok and _np.all(_np.isfinite(sol.q)):
                    self.committed_target = (local_x, local_z)
                    self.ctrl.set_target(sol.q)
                    # Freeze the base where it is — otherwise the last bit of
                    # min-jerk motion would shift the arm's world target and
                    # make the gripper "dance" around the ball.
                    self.world.drive_to(self.world.base_x)
            # End conditions. Use the CONTROLLER-TARGET arm state (same
            # source as the render) so the catch fires when the visible
            # gripper meets the ball, not when the lagging physics body
            # does. Otherwise the audience sees the jaws close on the ball
            # but physics disagrees → false miss.
            ball_pos, ball_vel = self.world.ball_state()
            arm = self.world.arm_state_from_target()
            ee_world = (arm.end_effector[0] + self.world.base_x,
                        arm.end_effector[1])
            dist = math.hypot(ee_world[0] - ball_pos[0], ee_world[1] - ball_pos[1])
            if dist < self.min_dist_this_pitch:
                self.min_dist_this_pitch = dist
            # Generous catch envelope: close enough → "snap" ball to EE.
            if dist < 0.30 and ball_pos[1] > 0.1:
                # Pass the arm-LOCAL EE — _snap_ball_to_ee adds base_x itself.
                self._snap_ball_to_ee(arm.end_effector)
                self.catch_count += 1
                self._set_state(self.STATE_COOLDOWN)
                return f"Caught! ({self.catch_count}/{self.attempt_count})"
            if ball_pos[1] <= 0.1 and not self.world._ball_active:
                self.min_dist_this_pitch = 1e9
                self._set_state(self.STATE_COOLDOWN)
                return f"Missed ({self.catch_count}/{self.attempt_count})."
            return (
                f"Tracking ball → ({pred.intercept_xz[0]:+.2f}, {pred.intercept_xz[1]:+.2f})"
                if pred.ok
                else "Tracking (ball out of reach)…"
            )

        if self.state == self.STATE_COOLDOWN:
            if elapsed > 1.3:
                self.committed_target = None
                self._set_state(self.STATE_ARMING)
                self.ctrl.set_target((0.7, -0.4, -0.3))
            if self.manual:
                return "Ready — click and drag for another throw."
            return "Ready for next pitch…"

        return ""

    # ---------------------------------------------------------- internals

    def _launch_new_ball(self) -> None:
        """Gentle lob from the right side toward the arm's reachable zone."""
        self.attempt_count += 1
        x0 = self.rng.uniform(1.3, 1.7)
        z0 = self.rng.uniform(0.4, 0.7)
        # Slow arc so the arm has 0.5-0.8s to position.
        vx = self.rng.uniform(-1.6, -1.1)
        vz = self.rng.uniform(3.2, 4.0)
        self._warned_unreachable = False
        self.world.launch_ball((x0, z0), (vx, vz))

    def _predict(self) -> Prediction:
        """Return the future (world) position where the ball will cross the
        catch height INTERCEPT_Z on its way DOWN, plus the time-to-intercept.
        Reachability / driving is handled by `update()` using the current
        base position.
        """
        (x0, z0), (vx, vz) = self.world.ball_state()
        # Solve z(t) = INTERCEPT_Z under constant gravity.
        # z(t) = z0 + vz*t - 0.5*g*t²
        a = -0.5 * GRAVITY
        b = vz
        c = z0 - INTERCEPT_Z
        disc = b * b - 4 * a * c
        if disc < 0:
            # Discriminant < 0 means the ball never reaches INTERCEPT_Z
            # (already past it on the way down with insufficient upward
            # velocity). One log per pitch so dev mode can see the geometry,
            # but the demo UI stays silent — the catcher will just keep
            # tracking until the ball lands or the state machine resets.
            if not self._warned_unreachable:
                print(
                    f"[catcher] no intercept: ball at z={z0:.2f}, vz={vz:.2f}, "
                    f"INTERCEPT_Z={INTERCEPT_Z:.2f} (disc={disc:.3f})",
                    file=sys.stderr,
                )
                self._warned_unreachable = True
            return Prediction(False, (0, 0), 0)
        sqrt_disc = math.sqrt(disc)
        # Two roots: first is ball going UP through plane, second going DOWN.
        t_up = (-b - sqrt_disc) / (2 * a) if a != 0 else 0
        t_down = (-b + sqrt_disc) / (2 * a) if a != 0 else 0
        # We always want the DOWNWARD crossing — that's when the ball lands
        # in the mitt. Pick the LARGER positive root.
        candidates = sorted([t for t in (t_up, t_down) if 0.02 < t < 2.5])
        if not candidates:
            return Prediction(False, (0, 0), 0)
        t = candidates[-1]   # latest (downward) crossing
        xi = x0 + vx * t
        return Prediction(True, (xi, INTERCEPT_Z), t)

    def _set_state(self, s: str) -> None:
        self.state = s
        self.state_entered_at = time.perf_counter()

    def _snap_ball_to_ee(self, ee_xz: tuple[float, float]) -> None:
        """Teleport the ball into the CENTER of the gripper jaws, using the
        CONTROLLER-TARGET arm state so the ball stays aligned with the
        rendered gripper rather than the physics-lagged EE.
        """
        arm = self.world.arm_state_from_target()
        hand_angle = arm.link_poses[-1].angle
        ee_tgt = arm.end_effector
        JAW_OFFSET = 0.22
        bx = ee_tgt[0] + JAW_OFFSET * math.cos(hand_angle) + self.world.base_x
        bz = ee_tgt[1] + JAW_OFFSET * math.sin(hand_angle)
        self.world.launch_ball((bx, bz), (0.0, 0.0))
