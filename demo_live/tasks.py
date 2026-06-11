"""High-level task executor: pick / place / stack atomic actions.

Each action is a *short program* of waypoints in end-effector space. The
executor walks through waypoints one at a time, using smooth cubic ease
interpolation between joint-space configurations. While a block is "held"
we update its pose to track the end effector each frame (no physical
grasp — this is a classroom demo, not a real robot).

The state machine ignores the ball-catch mode entirely; both can be
driven from the same arm but are switched by the main app's mode flag.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from . import ik
from .physics import BLOCK_HALF, Block, World

# ---------------------------------------------------------------- constants

STACK_X = -0.40                    # where towers get built (clear of yellow block)
PICK_HOVER_HEIGHT = 0.22           # meters above block before descending
APPROACH_DURATION = 1.1            # seconds per hover/descend/retreat segment
PLACE_TOLERANCE = 0.03             # meters

# Distance from end-effector origin to the CENTER of the gripper jaws. Must
# match `JAW_CENTER_OFFSET` in catcher / tasks update() — all three places
# that position a held block use this same number.
EE_TO_JAW_CENTER = 0.22


# ---------------------------------------------------------------- ease
#
# Animation-grade ease curve with anticipation + back ease-out. Real robots
# accelerate gradually and decelerate with a tiny mechanical settle; the
# bare minimum-jerk curve looks "machine-perfect" and reads as inhuman to
# an audience. We add:
#
#   - 0  ≤ t < 0.08 : wind-up — half-cosine reverse motion to -3%
#   - 0.08 ≤ t ≤ 1   : "back ease-out" — overshoots ~+6% mid-arc, settles to
#                      *exactly* 1.0 at t=1 (no snap-back needed)
#
# Net effect: the arm pulls back like a coiled spring, springs forward past
# the target, and lands cleanly. Position landing matches min-jerk; the
# velocity profile gains the anticipation + slight elastic settle.

WINDUP_END = 0.08
WINDUP_DEPTH = -0.03              # peak reverse motion during wind-up
BACK_S = 1.4                      # higher = more overshoot (1.4 → ~+6%)


def _ease_min_jerk(t: float) -> float:
    """Position easing on [WINDUP_DEPTH .. peak .. 1.0] over t ∈ [0, 1].

    Lands exactly on 1.0 at t=1 (no snap-back) so the held block placement
    is precise, while the mid-arc overshoot gives the motion a decisive,
    physical feel.
    """
    t = max(0.0, min(1.0, t))
    if t < WINDUP_END:
        u = t / WINDUP_END
        return WINDUP_DEPTH * 0.5 * (1 - math.cos(math.pi * u))
    # Back ease-out over (WINDUP_END, 1].
    u = (t - WINDUP_END) / (1.0 - WINDUP_END)
    u_shifted = u - 1.0
    return u_shifted * u_shifted * ((BACK_S + 1) * u_shifted + BACK_S) + 1.0


@dataclass
class Waypoint:
    """One arm pose to move to, plus optional side-effects when reached."""

    target_xz: tuple[float, float]
    hand_angle: float = -math.pi / 2     # hand points straight down by default
    duration: float = APPROACH_DURATION  # seconds to spend interpolating to this WP
    on_reach: Callable[[TaskExecutor], None] | None = None
    label: str = ""


# ---------------------------------------------------------------- executor

@dataclass
class TaskExecutor:
    world: World
    ctrl: object   # JointController (Newton-backed) OR FKJointController

    program: list[Waypoint] = field(default_factory=list)
    idx: int = 0
    segment_start: float = 0.0
    segment_q0: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    segment_q1: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    held: Block | None = None
    held_offset: tuple[float, float] = (0.0, 0.0)
    status_text: str = ""
    # Callables let multiple TaskExecutors drive different arms in the same
    # World — Arm A reads its mobile base_x, Arm B reads its fixed pillar X.
    # Both default to the legacy single-arm behavior so existing call sites
    # (newton_validation.py, demo_live tests) keep working.
    anchor_world_x: Callable[[], float] | None = None
    arm_state_provider: Callable[[], object] | None = None
    label: str = "A"  # display tag — useful when more than one executor exists

    @property
    def busy(self) -> bool:
        return self.idx < len(self.program)

    # ---------------------------------------------------- arm wiring

    def _anchor_x(self) -> float:
        """Current world X of the arm's shoulder anchor."""
        if self.anchor_world_x is not None:
            return self.anchor_world_x()
        return float(self.world.base_x)

    def _arm_state(self):
        """ArmState snapshot of whichever arm this executor drives."""
        if self.arm_state_provider is not None:
            return self.arm_state_provider()
        return self.world.arm_state_from_target()

    # ---------------------------------------------------- program builders

    def _local(self, world_xz: tuple[float, float]) -> tuple[float, float]:
        """World → arm-local X (shifted by anchor)."""
        return (world_xz[0] - self._anchor_x(), world_xz[1])

    def queue(self, waypoints: list[Waypoint]) -> None:
        if self.busy:
            self.program.extend(waypoints)
        else:
            self.program = list(waypoints)
            self.idx = 0
            if self.program:
                self._start_segment()

    def clear(self) -> None:
        self.program = []
        self.idx = 0
        self.held = None
        self.status_text = ""

    # ---------------------------------------------------- per-frame

    def _track_held_to_ee(self) -> None:
        """Snap the held block's world pose onto the gripper. Runs every
        frame, including while the executor is idle — without this, the
        block "floats" wherever it was last tracked when the previous plan
        finished, instead of following the arm back to rest pose."""
        if self.held is None:
            return
        arm = self._arm_state()
        ee_local = arm.end_effector
        hand_angle = arm.link_poses[-1].angle if arm.link_poses else 0.0
        bx = ee_local[0] + EE_TO_JAW_CENTER * math.cos(hand_angle) + self._anchor_x()
        bz = ee_local[1] + EE_TO_JAW_CENTER * math.sin(hand_angle)
        self._place_block(self.held, (bx, bz))

    def update(self, dt: float) -> None:
        # Track the held block to the gripper every frame, regardless of
        # whether a plan is running. Otherwise the block freezes mid-air
        # the moment a plan ends.
        self._track_held_to_ee()

        if not self.busy:
            return
        wp = self.program[self.idx]
        now = time.perf_counter()
        t = min(1.0, (now - self.segment_start) / max(1e-6, wp.duration))
        eased = _ease_min_jerk(t)
        q = self.segment_q0 + eased * (self.segment_q1 - self.segment_q0)
        self.ctrl.set_target(tuple(q))
        self.status_text = wp.label or f"Moving to waypoint {self.idx + 1}/{len(self.program)}"

        # On the final frame of a segment, snap the controller BEFORE tracking
        # the held block or firing the grab/release callback. Order matters:
        # (1) snap → (2) track block off the snapped pose → (3) fire callback.
        # This removes the 1–2 mm "flash" the audience would otherwise see
        # when the 22% slew filter finished converging.
        if t >= 1.0:
            self.ctrl.snap_to(tuple(self.segment_q1))

        if self.held is not None:
            arm = self._arm_state()
            ee_local = arm.end_effector
            hand_angle = arm.link_poses[-1].angle if arm.link_poses else 0.0
            import math as _m
            bx = ee_local[0] + EE_TO_JAW_CENTER * _m.cos(hand_angle) + self._anchor_x()
            bz = ee_local[1] + EE_TO_JAW_CENTER * _m.sin(hand_angle)
            self._place_block(self.held, (bx, bz))

        if t >= 1.0:
            if wp.on_reach is not None:
                wp.on_reach(self)
            self.idx += 1
            if self.idx < len(self.program):
                self._start_segment()

    def _start_segment(self) -> None:
        wp = self.program[self.idx]
        # Waypoints are authored in WORLD coordinates; convert to arm-local
        # before IK so the solution is relative to the current base position.
        local = self._local(wp.target_xz)
        sol = ik.solve_ik(
            local[0], local[1], hand_angle=wp.hand_angle, elbow_up=True
        )
        self.segment_q0 = self.ctrl.current_target.copy()
        self.segment_q1 = np.array(sol.q, dtype=np.float32)
        self.segment_start = time.perf_counter()

    # ---------------------------------------------------- helpers

    def _place_block(self, block: Block, xz: tuple[float, float]) -> None:
        """Write the block's pose in Python-side storage. Renderer reads from there."""
        self.world.move_block(block, xz)

    # ---------------------------------------------------- programs

    def make_pick(self, color: str) -> list[Waypoint]:
        """Move above block, descend, grip, retreat. Auto-drives closer if
        the block is outside the arm's current workspace.

        All waypoints target the *end effector*, not the block; the EE sits
        EE_TO_JAW_CENTER above the block center (hand points down, jaws
        wrap the block's sides). This means the block appears to sit IN the
        gripper every frame of the motion.
        """
        block = self.world.find_block(color)
        if block is None:
            return []
        bx, bz = block.xz
        prep = self._ensure_reachable((bx, bz))
        hover = (bx, bz + PICK_HOVER_HEIGHT + EE_TO_JAW_CENTER)
        grasp = (bx, bz + EE_TO_JAW_CENTER)

        def grab(exe: TaskExecutor) -> None:
            exe.held = block
            exe.held_offset = (0.0, -BLOCK_HALF - 0.01)
            # In real-blocks mode this makes the block KINEMATIC so it follows
            # the gripper; a no-op in teleport mode. Held tracking is identical
            # either way (move_block every frame).
            exe.world.grab_block(block)
            exe.status_text = f"Picked up {color} block"

        # Grab fires at the BOTTOM of descent — the moment the gripper jaws
        # straddle the block. That way the block's tracked position matches
        # its physical position (no teleport jump). The lift waypoint then
        # carries the block smoothly upward.
        return prep + [
            Waypoint(hover, duration=1.2, label=f"Approach {color}"),
            Waypoint(grasp, duration=0.7, on_reach=grab, label="Descend + grip"),
            Waypoint(hover, duration=0.5, label="Lift"),
        ]

    def _ensure_reachable(self, world_xz: tuple[float, float]) -> list[Waypoint]:
        """Prepend a drive waypoint that parks the base near `world_xz`.

        The drive's target is picked at PLAN TIME, but its motion fires at
        EXECUTE TIME — so the same stack program works no matter where the
        base happens to be when that waypoint runs (make_drive is a near-
        no-op if the base is already there).

        We bias the parking spot 0.45 m from the target so the arm reaches
        at an angle (avoids the straight-down shoulder singularity).

        Fixed-base arms (Arm B, with `anchor_world_x` set) cannot drive —
        and `make_drive` mutates the *primary* world base, which would yank
        Arm A around mid-task. So those arms early-return an empty prep:
        the IK target is either reachable from their fixed pose or it isn't.
        """
        if self.anchor_world_x is not None:
            return []
        OPTIMAL_REACH = 0.45
        # If target is near world centre, park on the outside. Otherwise park
        # on the closer side of the target.
        desired_base = world_xz[0] - OPTIMAL_REACH if world_xz[0] >= 0 else world_xz[0] + OPTIMAL_REACH
        desired_base = max(-1.6, min(1.6, desired_base))
        return self.make_drive(desired_base)

    def make_place(self, center_xz: tuple[float, float]) -> list[Waypoint]:
        """Carry the currently held block so its CENTER lands at `center_xz`.

        EE aims EE_TO_JAW_CENTER above the desired block center — same offset
        used everywhere else, so during descent the block slides cleanly down
        the stack without phasing through the blocks below.
        """
        hover = (center_xz[0], center_xz[1] + PICK_HOVER_HEIGHT + EE_TO_JAW_CENTER)
        down = (center_xz[0], center_xz[1] + EE_TO_JAW_CENTER)

        def release(exe: TaskExecutor) -> None:
            # The held block is already tracked to the jaw center this frame
            # (update() just ran). In real-blocks mode, flip it back to DYNAMIC
            # so it settles onto whatever is below it; in teleport mode this is a
            # no-op and the block simply stays where it IS visually (zero flash).
            if exe.held is not None:
                exe.world.release_block(exe.held)
            exe.held = None
            exe.status_text = "Released"

        prep = self._ensure_reachable(center_xz)
        # Release fires at the BOTTOM of descent (the moment the block rests
        # on the surface). The lift waypoint then retreats the empty
        # gripper upward. This mirrors the pick sequence — symmetric and
        # jump-free.
        return prep + [
            Waypoint(hover, duration=1.2, label="Move above target"),
            Waypoint(down, duration=0.7, on_reach=release, label="Descend + release"),
            Waypoint(hover, duration=0.5, label="Retreat"),
        ]

    def make_drive(self, target_x: float) -> list[Waypoint]:
        """Drive the mobile base to world `target_x` with a min-jerk profile.
        Duration matches the base's own curve so the executor waits until the
        robot has really arrived (no visual stutter)."""
        clamped = max(-1.6, min(1.6, float(target_x)))
        distance = abs(clamped - self.world.base_x)
        # 1.875 d / v_peak, with a floor so short moves still feel intentional.
        duration = max(0.5, 1.875 * distance / self.world.base_drive_speed)

        def start(exe: TaskExecutor) -> None:
            exe.world.drive_to(clamped)
            exe.status_text = f"Driving → x={clamped:+.2f}"

        def done(exe: TaskExecutor) -> None:
            exe.status_text = f"Arrived at x={clamped:+.2f}"

        rest = (0.7, 1.0)
        wp1 = Waypoint(rest, duration=0.01, on_reach=start, label=f"Drive to {clamped:+.2f}")
        wp2 = Waypoint(rest, duration=duration, on_reach=done, label="Driving")
        return [wp1, wp2]

    def make_stack(self, colors: list[str]) -> list[Waypoint]:
        """Stack the given colors at STACK_X. First color goes on bottom."""
        prog: list[Waypoint] = []
        home = (0.7, 1.0)    # rest between pick/place for visual clarity
        for i, color in enumerate(colors):
            # Block i's center sits at (2i+1) * BLOCK_HALF above ground.
            center_z = (2 * i + 1) * BLOCK_HALF
            prog += self.make_pick(color)
            prog += self.make_place((STACK_X, center_z))
            prog += [Waypoint(home, duration=0.7, label="Return")]
        return prog

    # ---------------------------------------------------------- gestures
    #
    # Decorative arm motions for the live demo. They drive the same EE-target
    # waypoint stack as the functional pick/place programs, so they share all
    # the IK + min-jerk infrastructure; the only difference is the chosen
    # target positions form an *expressive* trajectory instead of grabbing a
    # block. Audience-facing — no physical task being accomplished.

    GESTURE_HOME = (0.7, 1.0)         # neutral EE position (reused as anchor)
    GESTURE_DURATION = 0.55           # per-segment seconds — peppy but readable

    def make_wave(self, sweeps: int = 2) -> list[Waypoint]:
        """Raise the arm and sweep the end effector left-right `sweeps` times.

        Reads as "the robot is saying hi". The center of the wave sits a bit
        higher than the home pose so the motion is visible above the body."""
        up_center = (0.7, 1.35)
        sweep_left = (0.3, 1.20)
        sweep_right = (1.1, 1.20)
        prog: list[Waypoint] = [
            Waypoint(up_center, duration=self.GESTURE_DURATION, label="Wave up"),
        ]
        for i in range(max(1, int(sweeps))):
            prog.append(Waypoint(sweep_left, duration=self.GESTURE_DURATION,
                                 label=f"Wave left {i + 1}"))
            prog.append(Waypoint(sweep_right, duration=self.GESTURE_DURATION,
                                 label=f"Wave right {i + 1}"))
        prog.append(Waypoint(self.GESTURE_HOME, duration=self.GESTURE_DURATION,
                             label="Wave done"))
        return prog

    def make_point(self, direction: str = "left") -> list[Waypoint]:
        """Extend the arm toward an audience-relative direction and hold.

        Accepts "left" / "right" / "audience" (interpreted as "straight out
        toward the viewer", which in our XZ projection is roughly up-and-out
        on the workspace side closer to camera). Other strings collapse to
        "left" so the gesture always lands somewhere visible."""
        if direction == "right":
            target = (1.2, 1.05)
        elif direction == "audience":
            target = (0.55, 1.30)
        else:                                 # "left" + any unknown
            target = (-0.05, 1.05)
        return [
            Waypoint(target, duration=0.7, label=f"Point {direction}"),
            # Hold beat — re-issuing the same target lets the executor "stay
            # there" for the audience to follow. Min-jerk converges instantly
            # so the held duration is dominated by `duration`.
            Waypoint(target, duration=1.5, label="(holding)"),
            Waypoint(self.GESTURE_HOME, duration=self.GESTURE_DURATION,
                     label="Return"),
        ]

    def make_bow(self, depth: float = 0.35) -> list[Waypoint]:
        """Bend the arm forward and down — the robot equivalent of a bow."""
        depth = max(0.15, min(0.55, float(depth)))
        dip = (0.65, self.GESTURE_HOME[1] - depth)
        return [
            Waypoint(dip, duration=0.6, label="Bowing"),
            Waypoint(dip, duration=0.6, label="(held)"),
            Waypoint(self.GESTURE_HOME, duration=0.6, label="Rise"),
        ]

    def make_dance(self, beats: int = 4) -> list[Waypoint]:
        """A short rhythmic sequence — `beats` evenly-spaced poses that trace
        a small box around the home position. 4 beats = ~2.2s of motion."""
        n = max(2, int(beats))
        # Pre-canned offset corners; cycled by index modulo 4.
        corners = [
            (0.55, 1.20),   # upper-left
            (0.85, 1.20),   # upper-right
            (0.85, 0.85),   # lower-right
            (0.55, 0.85),   # lower-left
        ]
        prog = [
            Waypoint(corners[i % 4], duration=self.GESTURE_DURATION,
                     label=f"Dance beat {i + 1}")
            for i in range(n)
        ]
        prog.append(Waypoint(self.GESTURE_HOME, duration=self.GESTURE_DURATION,
                             label="Dance done"))
        return prog

