"""Newton physics world for the demo.

A planar 3-link arm + a ground plane + a handful of stackable blocks.
All motion happens in the world X-Z plane (Y is into the screen).
We expose joint angles and body poses in world coordinates for the renderer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import newton
import numpy as np
import warp as wp

from . import config as C

# Arm geometry (meters)
LINK_LENGTHS = (0.55, 0.45, 0.30)    # upper / fore / hand
LINK_HALF_W = 0.035                   # link half-width (thickness)
TOTAL_REACH = sum(LINK_LENGTHS)

# "Ready" pose — arm raised, slightly bent, hand forward. Joint angles (rad)
# accumulate along the chain: theta_world_i = sum(q[0..i]).
REST_POSE = (1.2, -1.0, -0.2)

# Block dimensions — larger than a real cube for classroom visibility.
BLOCK_HALF = 0.10                     # 20 cm cubes

# Hard ceiling for ball launch velocity (m/s). A human mouse-drag tops out
# around 12 m/s on a 1920-px viewport; 20 m/s leaves headroom for a fast
# throw while preventing pathological inputs (very long flicks, scripted
# typos like (1e6, 1e6)) from blowing the ball through the workspace in
# one frame.
MAX_BALL_SPEED = 20.0


@dataclass
class Block:
    """One colored cube. Kept outside Newton physics — pose is stored in Python
    and used directly by the renderer + task executor. This avoids the XPBD
    solver spraying teleported blocks across the world."""

    color: str
    xz: tuple[float, float]      # world (x, z) of CENTER
    angle: float = 0.0           # Y-axis rotation (for future spin effects)


@dataclass
class Ball:
    """The ball used in MPC catching mode."""

    body_id: int
    radius: float = 0.05


@dataclass
class LinkPose:
    """A link's body frame in the world (center, rotation about Y)."""

    center_xz: tuple[float, float]
    angle: float


@dataclass
class ArmState:
    """Snapshot of the arm each frame for the renderer."""

    joint_angles: np.ndarray          # (3,) radians
    link_world_ends: list[tuple[float, float]]   # [(x, z), ...] per link end, + base
    end_effector: tuple[float, float]
    link_poses: list[LinkPose]         # one per arm link, from Newton's body_q


def fk_chain(
    q_arm: np.ndarray,
    anchor_local_xz: tuple[float, float] = (0.0, C.ARM_BASE_Z),
    link_lengths: tuple[float, ...] = LINK_LENGTHS,
) -> ArmState:
    """Forward-kinematics on a 3-link planar chain.

    Returns positions in the *arm-local* frame whose origin is the world X
    position of whoever owns the arm (the mobile base for Arm A, the fixed
    pillar for Arm B). The renderer composites the local frame onto the
    world via `local_to_screen(x, z, base_offset)`.
    """
    link_poses: list[LinkPose] = []
    link_ends: list[tuple[float, float]] = [anchor_local_xz]
    x_prev, z_prev = anchor_local_xz
    theta = 0.0
    for i, length in enumerate(link_lengths):
        theta += float(q_arm[i])
        x_tip = x_prev + length * np.cos(theta)
        z_tip = z_prev + length * np.sin(theta)
        cx = (x_prev + x_tip) / 2
        cz = (z_prev + z_tip) / 2
        link_poses.append(LinkPose(center_xz=(float(cx), float(cz)),
                                    angle=float(theta)))
        link_ends.append((float(x_tip), float(z_tip)))
        x_prev, z_prev = x_tip, z_tip

    return ArmState(
        joint_angles=np.asarray(q_arm, dtype=np.float32),
        link_world_ends=link_ends,
        end_effector=link_ends[-1],
        link_poses=link_poses,
    )


@dataclass
class FKArmRig:
    """Render-only secondary arm — same kinematics as the primary, but its
    state is computed in pure Python (no Newton XPBD). Anchored at a fixed
    world X position; the existing render pipeline composites it onto the
    scene via local_to_screen(..., anchor_world_x).
    """

    anchor_world_x: float                                   # world frame mount X
    link_lengths: tuple[float, ...] = LINK_LENGTHS
    joint_target: np.ndarray = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.joint_target is None:
            self.joint_target = np.array(REST_POSE, dtype=np.float32)

    def arm_state_from_target(self) -> ArmState:
        return fk_chain(self.joint_target,
                        anchor_local_xz=(0.0, C.ARM_BASE_Z),
                        link_lengths=self.link_lengths)


class World:
    """Owns the Newton model, state, solver and provides frame-step + queries."""

    def __init__(self, block_layout: list[tuple[str, float, float]] | None = None) -> None:
        builder = newton.ModelBuilder()

        # --- Arm: anchored at (0, 0, ARM_BASE_Z) ---
        self._link_ids: list[int] = []
        joint_ids: list[int] = []
        parent = -1
        anchor_x = 0.0
        anchor_z = C.ARM_BASE_Z
        for i, length in enumerate(LINK_LENGTHS):
            link = builder.add_link()
            builder.add_shape_box(link, hx=length / 2, hy=LINK_HALF_W, hz=LINK_HALF_W)
            # Revolute joint around Y axis; first joint is world-fixed.
            if parent == -1:
                parent_xform = wp.transform(
                    p=wp.vec3(anchor_x, 0.0, anchor_z), q=wp.quat_identity()
                )
            else:
                parent_xform = wp.transform(
                    p=wp.vec3(LINK_LENGTHS[i - 1] / 2, 0.0, 0.0), q=wp.quat_identity()
                )
            child_xform = wp.transform(p=wp.vec3(-length / 2, 0.0, 0.0), q=wp.quat_identity())
            joint = builder.add_joint_revolute(
                parent=parent,
                child=link,
                axis=wp.vec3(0.0, -1.0, 0.0),
                parent_xform=parent_xform,
                child_xform=child_xform,
                target_pos=REST_POSE[i],
                target_ke=5000.0,
                target_kd=150.0,
                limit_lower=-np.pi,
                limit_upper=np.pi,
            )
            self._link_ids.append(link)
            joint_ids.append(joint)
            parent = link
        builder.add_articulation(joint_ids, label="arm")

        # --- Ground ---
        builder.add_ground_plane()

        # --- Blocks ---
        # Layout positions are WORLD-x of each block's center, spaced 0.4 m
        # apart so there's a clear visible gap between cubes (block side is
        # 0.20 m; 0.4 m centers → 0.2 m gap, roughly one block wide).
        if block_layout is None:
            block_layout = [
                ("red", 0.70, 0.0),
                ("green", 1.10, 0.0),
                ("blue", 1.50, 0.0),
                ("yellow", -0.95, 0.0),
                # Dedicated workpiece for Arm B's idle pick-place loop.
                # Lives in Arm B's reachable zone (anchor x=2.40, reach
                # ~1 m) so it's the *only* block Arm B can pick up
                # without conflict with the four teaching colors.
                ("workpiece", 2.00, 0.0),
            ]
        self._blocks: list[Block] = [
            Block(color=color, xz=(x, BLOCK_HALF + z)) for color, x, z in block_layout
        ]
        # Snapshot the initial block positions so the out-of-bounds
        # auto-recovery in __main__ can teleport a stray block back to its
        # spawn slot without inventing a new layout.
        self._block_init_xz: list[tuple[float, float]] = [b.xz for b in self._blocks]

        # --- One ball for MPC catching (offscreen at rest until launched) ---
        ball_body = builder.add_body(mass=0.08)
        builder.add_shape_sphere(ball_body, radius=0.05)
        self._ball = Ball(body_id=ball_body, radius=0.05)

        # --- Finalize ---
        self.model = builder.finalize()
        self.solver = newton.solvers.SolverXPBD(self.model, iterations=20)
        self.state_0 = self.model.state()
        self.state_1 = self.model.state()
        self.control = self.model.control()

        # --- Mobile base state (Python-side; Newton arm stays at local origin) ---
        self.base_x: float = 0.0            # world x of the arm base
        self.base_target_x: float = 0.0     # where we're driving to
        self.base_drive_speed: float = 2.5  # m/s peak (min-jerk profile) —
                                            # fast enough to chase 1-sec ball flights
        self.track_rotation: float = 0.0    # radians, for wheel sprite rotation
        # Min-jerk drive animation parameters (set by drive_to).
        self._drive_start_x: float = 0.0
        self._drive_start_time: float = 0.0
        self._drive_duration: float = 0.0

        # Start arm at rest pose so it doesn't swing up from a flat start.
        q = self.model.joint_q.numpy()
        q[:3] = np.array(REST_POSE, dtype=np.float32)
        self.model.joint_q.assign(q)

        newton.eval_fk(self.model, self.model.joint_q, self.model.joint_qd, self.state_0)

        # Ball starts parked off-screen.
        bq = self.state_0.body_q.numpy().copy()
        bq[self._ball.body_id] = np.array([10.0, 0.0, 5.0, 0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        self.state_0.body_q.assign(bq)

        # Gravity defaults to (0, 0, -9.81) which is correct for Z-up.
        self.sim_dt = 1.0 / 240.0
        self.substeps = 4

    # --- public API -------------------------------------------------

    def step(self) -> None:
        """Advance physics by one render frame (= `substeps` sim-steps)."""
        for _ in range(self.substeps):
            contacts = self.model.collide(self.state_0)
            self.solver.step(self.state_0, self.state_1, self.control, contacts, self.sim_dt)
            self.state_0, self.state_1 = self.state_1, self.state_0

    def arm_state_from_target(self) -> ArmState:
        """Compute link poses by forward-kinematics of the CONTROLLER'S
        current target, not the noisy physics body_q.

        Why: Newton's XPBD solver oscillates slightly around PD targets, and
        those oscillations translate into gripper jitter. Since we don't rely
        on arm-object physical contact for any gameplay (blocks + ball are
        kinematic), the render can safely use the smooth commanded pose.
        """
        ctrl = self.control
        if ctrl.joint_target_pos is None:
            q_arm = self.model.joint_q.numpy()[:3].copy()
        else:
            q_arm = ctrl.joint_target_pos.numpy()[:3].copy()

        if not np.all(np.isfinite(q_arm)):
            q_arm = np.array(REST_POSE, dtype=np.float32)

        # Forward kinematics — angle accumulates along the chain.
        link_poses: list[LinkPose] = []
        link_ends: list[tuple[float, float]] = [(0.0, C.ARM_BASE_Z)]
        x_prev, z_prev = 0.0, C.ARM_BASE_Z
        theta = 0.0
        for i, length in enumerate(LINK_LENGTHS):
            theta += float(q_arm[i])
            x_tip = x_prev + length * np.cos(theta)
            z_tip = z_prev + length * np.sin(theta)
            cx = (x_prev + x_tip) / 2
            cz = (z_prev + z_tip) / 2
            link_poses.append(LinkPose(center_xz=(float(cx), float(cz)), angle=float(theta)))
            link_ends.append((float(x_tip), float(z_tip)))
            x_prev, z_prev = x_tip, z_tip

        return ArmState(
            joint_angles=q_arm,
            link_world_ends=link_ends,
            end_effector=link_ends[-1],
            link_poses=link_poses,
        )

    def arm_state(self) -> ArmState:
        """Compute joint angles, link poses, and end effector from Newton's body_q.

        Using Newton's authoritative pose (not custom FK) guarantees the render
        matches the physics collision shapes. If the solver has produced any
        NaN/inf (rare numerical instability on large target jumps), we fall
        back to a safe rest-pose snapshot instead of propagating NaN into the
        renderer, which would crash pygame's int conversion.
        """
        newton.eval_ik(self.model, self.state_0, self.model.joint_q, self.model.joint_qd)
        q = self.model.joint_q.numpy()[:3].copy()

        bq = self.state_0.body_q.numpy()
        link_poses: list[LinkPose] = []
        link_ends: list[tuple[float, float]] = [(0.0, C.ARM_BASE_Z)]
        bad = False
        for i, length in enumerate(LINK_LENGTHS):
            tf = bq[self._link_ids[i]]
            if not np.all(np.isfinite(tf)):
                bad = True
                break
            cx, cz = float(tf[0]), float(tf[2])
            qy, qw = float(tf[4]), float(tf[6])
            angle = 2.0 * np.arctan2(qy, qw)
            link_poses.append(LinkPose(center_xz=(cx, cz), angle=angle))
            ex = cx + 0.5 * length * np.cos(angle)
            ez = cz + 0.5 * length * np.sin(angle)
            link_ends.append((ex, ez))

        if bad:
            # Hard reset the physics state to REST_POSE so rendering can continue.
            self._reset_arm_to_rest()
            return self.arm_state()

        return ArmState(
            joint_angles=q,
            link_world_ends=link_ends,
            end_effector=link_ends[-1],
            link_poses=link_poses,
        )

    def _reset_arm_to_rest(self) -> None:
        """Recover from a NaN in the physics state by re-seeding the arm."""
        q = self.model.joint_q.numpy().copy()
        qd = self.model.joint_qd.numpy().copy()
        q[:3] = np.array(REST_POSE, dtype=np.float32)
        qd[:3] = 0.0
        self.model.joint_q.assign(q)
        self.model.joint_qd.assign(qd)
        newton.eval_fk(self.model, self.model.joint_q, self.model.joint_qd, self.state_0)

    def block_poses(self) -> list[tuple[Block, tuple[float, float], float]]:
        """Return [(block, (x, z), rotation_rad)] for each block, in world frame."""
        return [(b, b.xz, b.angle) for b in self._blocks]

    def move_block(self, block: Block, xz: tuple[float, float]) -> None:
        block.xz = (float(xz[0]), float(xz[1]))

    # --- Mobile base -----------------------------------------------

    def drive_to(self, target_x: float) -> None:
        """Queue a smooth (min-jerk) translation of the base to world x."""
        import time
        self.base_target_x = max(-1.8, min(1.8, float(target_x)))
        distance = abs(self.base_target_x - self.base_x)
        # Duration scaled so the peak velocity matches base_drive_speed;
        # with the min-jerk profile peak = 1.875 × avg, so duration = 1.875 d / v.
        self._drive_start_x = self.base_x
        self._drive_start_time = time.perf_counter()
        self._drive_duration = max(0.001, 1.875 * distance / self.base_drive_speed)

    def integrate_base(self, dt: float) -> None:
        """Advance the base via the stored min-jerk curve and spin tracks."""
        import time
        if abs(self.base_target_x - self.base_x) < 1e-4:
            self.base_x = self.base_target_x
            return
        t = (time.perf_counter() - self._drive_start_time) / max(1e-6, self._drive_duration)
        t = max(0.0, min(1.0, t))
        # Min-jerk position profile: 10t³ - 15t⁴ + 6t⁵
        alpha = t * t * t * (10 - 15 * t + 6 * t * t)
        old_x = self.base_x
        self.base_x = self._drive_start_x + alpha * (self.base_target_x - self._drive_start_x)
        move = self.base_x - old_x
        wheel_r = 0.07
        self.track_rotation += move / wheel_r

    @property
    def is_driving(self) -> bool:
        return abs(self.base_target_x - self.base_x) > 1e-4

    def find_block(self, color: str) -> Block | None:
        for b in self._blocks:
            if b.color == color:
                return b
        return None

    # --- Ball API --------------------------------------------------
    #
    # XPBD is position-based and ignores initial velocity, so we drive the
    # ball analytically in Python and write its pose into state_0 each frame.
    # This also keeps the trajectory clean (no accidental arm deflection).

    _ball_pos: tuple[float, float] = (10.0, 5.0)
    _ball_vel: tuple[float, float] = (0.0, 0.0)
    _ball_active: bool = False

    def launch_ball(self, start_xz: tuple[float, float], velocity_xz: tuple[float, float]) -> None:
        # Clamp z to a sane vertical range — a launch from z<0 starts the ball
        # below the floor (catcher can never intercept), and z>2.0 puts it
        # above the visible viewport (audience can't see it land). Clamping
        # here is a cheap safety net for noisy mouse-drag throws and for
        # third-party callers (rehearsal scripts, tests) that haven't
        # validated their own coordinates.
        x = float(start_xz[0])
        z = float(start_xz[1])
        if z < 0.0:
            z = 0.0
        elif z > 2.0:
            z = 2.0
        # Clamp velocity magnitude to MAX_BALL_SPEED so a pathological mouse
        # drag (or a misbehaving rehearsal script) can't fling the ball off
        # the screen in one frame. 20 m/s comfortably exceeds anything a
        # human can drag (drag-scale 4 × viewport-meters → ~12 m/s peak)
        # while leaving headroom for fast throws.
        vx = float(velocity_xz[0])
        vz = float(velocity_xz[1])
        vmag_sq = vx * vx + vz * vz
        if vmag_sq > MAX_BALL_SPEED * MAX_BALL_SPEED:
            scale = MAX_BALL_SPEED / math.sqrt(vmag_sq)
            vx *= scale
            vz *= scale
        self._ball_pos = (x, z)
        self._ball_vel = (vx, vz)
        self._ball_active = True
        self._write_ball_pose()

    def park_ball(self) -> None:
        self._ball_pos = (10.0, 5.0)
        self._ball_vel = (0.0, 0.0)
        self._ball_active = False
        self._write_ball_pose()

    def integrate_ball(self, dt: float, gravity: float = 9.81) -> None:
        """Advance the ball one frame using closed-form ballistic integration."""
        if not self._ball_active:
            return
        x, z = self._ball_pos
        vx, vz = self._ball_vel
        x = x + vx * dt
        z = z + vz * dt - 0.5 * gravity * dt * dt
        vz = vz - gravity * dt
        # Stop when hit ground.
        if z <= 0.05:
            z = 0.05
            vx = 0.0
            vz = 0.0
            self._ball_active = False
        self._ball_pos = (x, z)
        self._ball_vel = (vx, vz)
        self._write_ball_pose()

    def ball_state(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return self._ball_pos, self._ball_vel

    def _write_ball_pose(self) -> None:
        bq = self.state_0.body_q.numpy().copy()
        tf = np.zeros(7, dtype=np.float32)
        tf[0] = self._ball_pos[0]
        tf[1] = 0.0
        tf[2] = self._ball_pos[1]
        tf[6] = 1.0
        bq[self._ball.body_id] = tf
        self.state_0.body_q.assign(bq)

    # --- Convenience ------------------------------------------------

    @property
    def blocks(self) -> list[Block]:
        return self._blocks

    @property
    def ball(self) -> Ball:
        return self._ball

    @property
    def link_lengths(self) -> tuple[float, ...]:
        return LINK_LENGTHS


def world_to_screen(x_m: float, z_m: float) -> tuple[int, int]:
    """World (X, Z in meters, Z-up) -> pygame screen (x, y in pixels, y-down)."""
    sx = C.ORIGIN_X_PX + int(x_m * C.PX_PER_M)
    sy = C.GROUND_Y_PX - int(z_m * C.PX_PER_M)
    return sx, sy


def local_to_screen(x_m: float, z_m: float, base_x: float = 0.0) -> tuple[int, int]:
    """Arm-local frame -> screen, shifted by the current base_x offset.

    Used for anything attached to the robot (arm links, gripper, base chassis).
    Blocks and the ball live in world frame, so they use `world_to_screen`
    directly.
    """
    return world_to_screen(x_m + base_x, z_m)


def screen_to_world(sx: int, sy: int) -> tuple[float, float]:
    """Inverse of world_to_screen — used by mouse event handlers to turn
    clicks into world (x, z) coordinates."""
    x_m = (sx - C.ORIGIN_X_PX) / C.PX_PER_M
    z_m = (C.GROUND_Y_PX - sy) / C.PX_PER_M
    return x_m, z_m
