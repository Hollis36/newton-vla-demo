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
from newton.solvers import SolverNotifyFlags

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

# Solver tuning (lever-1 profiling). Both modes use the same
# SUBSTEPS × SIM_DT = 1/60 s so physics runs at wall-clock speed; this was
# verified to leave the (controller-driven) rendered arm choreography
# bit-identical regardless of iteration count.
#   • Real blocks need enough iterations for stable stacks (+ light contact
#     relaxation, matching newton's pyramid example).
#   • Teleport mode only PD-tracks the arm, whose body_q is never rendered
#     (the renderer uses arm_state_from_target), so a minimal count suffices.
REAL_BLOCKS_ITERATIONS = 8
TELEPORT_ITERATIONS = 2
SUBSTEPS = 2
SIM_DT = 1.0 / 120.0
REAL_BLOCKS_RELAXATION = 0.8

# Hard ceiling for ball launch velocity (m/s). A human mouse-drag tops out
# around 12 m/s on a 1920-px viewport; 20 m/s leaves headroom for a fast
# throw while preventing pathological inputs (very long flicks, scripted
# typos like (1e6, 1e6)) from blowing the ball through the workspace in
# one frame.
MAX_BALL_SPEED = 20.0


@dataclass
class Block:
    """One colored cube.

    In the default (teleport) mode the pose lives in Python and is consumed
    directly by the renderer + task executor, which avoids the XPBD solver
    spraying teleported blocks across the world. In real-blocks mode `body_id`
    points at a genuine Newton rigid body and `xz`/`angle` are refreshed from it
    each frame (see `World._sync_blocks_from_physics`)."""

    color: str
    xz: tuple[float, float]      # world (x, z) of CENTER
    angle: float = 0.0           # Y-axis rotation (radians; real-blocks topple)
    body_id: int | None = None   # Newton rigid-body id in real-blocks mode, else None


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

    def __init__(
        self,
        block_layout: list[tuple[str, float, float]] | None = None,
        *,
        real_blocks: bool = False,
    ) -> None:
        builder = newton.ModelBuilder()
        # When True, the colored blocks are genuine Newton rigid bodies (they
        # stack, topple and collide). When False (default), they stay Python-side
        # kinematic dataclasses teleported by the task executor — the original,
        # rehearsal-proven behavior. See grab_block / release_block / move_block.
        self._real_blocks = real_blocks

        # --- Arm: anchored at (0, 0, ARM_BASE_Z) ---
        self._link_ids: list[int] = []
        self._arm_shape_ids: list[int] = []
        joint_ids: list[int] = []
        parent = -1
        anchor_x = 0.0
        anchor_z = C.ARM_BASE_Z
        for i, length in enumerate(LINK_LENGTHS):
            link = builder.add_link()
            self._arm_shape_ids.append(builder.shape_count)
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
        # Default layout comes from config.BLOCK_LAYOUT — the single source
        # of truth also feeding the VLA parser's drive targets and Claude's
        # system prompt, so the language side can never drift from physics.
        if block_layout is None:
            block_layout = list(C.BLOCK_LAYOUT)
        self._blocks: list[Block] = [
            Block(color=color, xz=(x, BLOCK_HALF + z)) for color, x, z in block_layout
        ]
        # Snapshot the initial block positions so the out-of-bounds
        # auto-recovery in __main__ can teleport a stray block back to its
        # spawn slot without inventing a new layout.
        self._block_init_xz: list[tuple[float, float]] = [b.xz for b in self._blocks]

        # In real-blocks mode each Block gets a genuine rigid body (box) so it
        # collides, stacks and topples. The body id is stored on the Block
        # itself (looked up by identity, never by value — see grab_block).
        # `_held_body_ids` tracks which block bodies a gripper currently holds
        # (KINEMATIC), so a second grab / a release-without-grab / an
        # out-of-bounds recovery can't corrupt a held block.
        self._block_shape_ids: list[int] = []
        self._held_body_ids: set[int] = set()
        if real_blocks:
            for b in self._blocks:
                bx, bz = b.xz
                body = builder.add_body(
                    xform=wp.transform(p=wp.vec3(bx, 0.0, bz), q=wp.quat_identity())
                )
                self._block_shape_ids.append(builder.shape_count)
                builder.add_shape_box(body, hx=BLOCK_HALF, hy=BLOCK_HALF, hz=BLOCK_HALF)
                b.body_id = body

        # --- One ball for MPC catching (offscreen at rest until launched) ---
        ball_body = builder.add_body(mass=0.08)
        self._ball_shape_id = builder.shape_count
        builder.add_shape_sphere(ball_body, radius=0.05)
        self._ball = Ball(body_id=ball_body, radius=0.05)

        # --- Real-block collision filtering ---
        # Blocks collide with each other and the ground (real stacking / toppling)
        # but NOT with the arm links or the analytic ball: the arm drives a held
        # block via the kinematic-grasp abstraction, so physical arm↔block contact
        # would only fight the PD controller. Filter those pairs out explicitly.
        if real_blocks:
            for block_shape in self._block_shape_ids:
                for arm_shape in self._arm_shape_ids:
                    builder.add_shape_collision_filter_pair(arm_shape, block_shape)
                builder.add_shape_collision_filter_pair(self._ball_shape_id, block_shape)

        # --- Finalize ---
        self.model = builder.finalize()
        self.solver = newton.solvers.SolverXPBD(
            self.model,
            iterations=REAL_BLOCKS_ITERATIONS if real_blocks else TELEPORT_ITERATIONS,
            **({"rigid_contact_relaxation": REAL_BLOCKS_RELAXATION} if real_blocks else {}),
        )
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
        self.sim_dt = SIM_DT
        self.substeps = SUBSTEPS

        # Teleport mode never needs contact resolution: the arm is a
        # world-anchored PD chain in free space, blocks are kinematic Python,
        # the ball is analytic, and the *rendered* arm comes from the controller
        # (not body_q). So we skip the per-substep collision pipeline — which the
        # profiler showed is the dominant kernel-launch cost — and reuse one
        # empty contacts buffer instead. Measured: step() 4.7 ms → 1.0 ms.
        # Real-blocks mode keeps live collision (blocks stack via contacts).
        self._empty_contacts = None if real_blocks else self.model.collide(self.state_0)

    # --- public API -------------------------------------------------

    def step(self) -> None:
        """Advance physics by one render frame (= `substeps` sim-steps)."""
        for _ in range(self.substeps):
            contacts = self.model.collide(self.state_0) if self._real_blocks else self._empty_contacts
            self.solver.step(self.state_0, self.state_1, self.control, contacts, self.sim_dt)
            self.state_0, self.state_1 = self.state_1, self.state_0
        if self._real_blocks:
            self._sync_blocks_from_physics()

    def _sync_blocks_from_physics(self) -> None:
        """Copy each real block body's pose back into its Block dataclass so
        `block_poses()`, the renderer, telemetry and the out-of-bounds check all
        read fresh positions and rotations (including toppled, rotated blocks)."""
        bq = self.state_0.body_q.numpy()
        for block in self._blocks:
            if block.body_id is None:
                continue
            tf = bq[block.body_id]
            block.xz = (float(tf[0]), float(tf[2]))
            block.angle = 2.0 * math.atan2(float(tf[4]), float(tf[6]))

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

    @property
    def real_blocks(self) -> bool:
        """True when blocks are genuine rigid bodies (``--real-blocks``)."""
        return self._real_blocks

    def recover_out_of_bounds(self) -> None:
        """Teleport any block that physics flung way off screen back to its
        spawn slot. Called once per frame by the main loop. Held blocks are
        never recovered: in real-blocks mode the carry already prescribes
        their pose every frame, and snapping them to spawn mid-carry would
        make them stutter between the jaw and the slot. The 3.0 m threshold
        comfortably contains the teaching blocks (max |x| ≈ 1.5) and Arm B's
        zone (1.50 ↔ 2.50) while still catching anything truly flung away."""
        for idx, block in enumerate(self._blocks):
            if self.is_block_held(block):
                continue
            out_of_bounds = (abs(block.xz[0]) > 3.0
                             or block.xz[1] < -0.5
                             or block.xz[1] > 2.5)
            if out_of_bounds and idx < len(self._block_init_xz):
                self.move_block(block, self._block_init_xz[idx])

    def move_block(self, block: Block, xz: tuple[float, float]) -> None:
        """Set a block's world (x, z). In real-blocks mode this writes the rigid
        body's pose (used for the held KINEMATIC block, which the gripper drives,
        and for out-of-bounds recovery); the Block dataclass is kept in sync so
        Python-side readers stay correct."""
        x, z = float(xz[0]), float(xz[1])
        if self._real_blocks and block.body_id is not None:
            self._write_block_pose(block.body_id, x, z)
        block.xz = (x, z)

    def _write_block_pose(self, body_id: int, x: float, z: float) -> None:
        """Prescribe a block body's pose upright at (x, 0, z) and zero its
        velocity, so a kinematic held block tracks the gripper without drift."""
        bq = self.state_0.body_q.numpy().copy()
        bq[body_id] = np.array([x, 0.0, z, 0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        self.state_0.body_q.assign(bq)
        qd = self.state_0.body_qd.numpy().copy()
        qd[body_id] = 0.0
        self.state_0.body_qd.assign(qd)

    def grab_block(self, block: Block) -> None:
        """Attach a block to the gripper. In real-blocks mode the body becomes
        KINEMATIC: the solver passes its prescribed pose (written by move_block
        each frame) straight through while other blocks still collide against it.
        No-op in teleport mode, where holding is purely a Python reference.

        Refuses to re-grab an already-held block, so two arms targeting the same
        block (or a double-fired callback) can't double-toggle its flag."""
        if not self._real_blocks or block.body_id is None:
            return
        if block.body_id in self._held_body_ids:
            return
        self._held_body_ids.add(block.body_id)
        self._set_block_flag(block.body_id, newton.BodyFlags.KINEMATIC)

    def release_block(self, block: Block) -> None:
        """Detach a block from the gripper: flip back to DYNAMIC so it settles
        under gravity onto whatever is below it. No-op in teleport mode, or if
        the block isn't currently held (release-without-grab)."""
        if not self._real_blocks or block.body_id is None:
            return
        if block.body_id not in self._held_body_ids:
            return
        self._held_body_ids.discard(block.body_id)
        self._set_block_flag(block.body_id, newton.BodyFlags.DYNAMIC)

    def is_block_held(self, block: Block) -> bool:
        """True if a gripper currently holds this block (KINEMATIC). Used by the
        out-of-bounds recovery so it never fights a block mid-carry."""
        return block.body_id is not None and block.body_id in self._held_body_ids

    def _set_block_flag(self, body_id: int, flag: newton.BodyFlags) -> None:
        # O(body_count) host round-trip + a model-changed refresh per grasp event;
        # negligible at ~5 blocks but don't scale this to hundreds of bodies.
        flags = self.model.body_flags.numpy().copy()
        flags[body_id] = int(flag)
        self.model.body_flags.assign(flags)
        # XPBD precomputes its kinematic set; notify it so the toggle takes effect.
        self.solver.notify_model_changed(SolverNotifyFlags.BODY_PROPERTIES)

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
