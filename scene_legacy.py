"""High-level scene renderer: arm, blocks, ground, chrome (header, panel, footer)."""

from __future__ import annotations

import math

import pygame

from . import config as C
from . import render as R
from .physics import BLOCK_HALF, LINK_HALF_W, World, local_to_screen, world_to_screen


def draw_ground(surface: pygame.Surface) -> None:
    """Horizontal line at z=0, with hatched 'floor'."""
    left = (0, C.GROUND_Y_PX)
    right = (C.VIEWPORT_WIDTH, C.GROUND_Y_PX)
    R.sketch_line(surface, C.INK, left, right, width=C.LINE_WIDTH_MEDIUM, wobble=0.3, seed=1001)
    # Hatching below
    for x in range(0, C.VIEWPORT_WIDTH, 30):
        a = (x, C.GROUND_Y_PX + 4)
        b = (x - 16, C.GROUND_Y_PX + 20)
        pygame.draw.line(surface, C.INK_SOFT, a, b, 2)


def draw_arm_base(surface: pygame.Surface, world: World | None = None) -> None:
    """Tracked (tank-style) mobile robot base. Spins wheels when driving."""
    base_offset = world.base_x if world is not None else 0.0
    wheel_rot = world.track_rotation if world is not None else 0.0
    base_x, base_y = local_to_screen(0.0, 0.0, base_offset)
    top_x, top_y = local_to_screen(0.0, C.ARM_BASE_Z, base_offset)

    # --- Tracks (two parallel ovals on the ground) ---
    track_h = 34
    track_w = 180
    # Track sits "straddling" the ground line: half above, half below.
    track_top = base_y - track_h
    track_bottom = base_y
    # Rounded rectangle for each track (use two circles + rect).
    left = base_x - track_w // 2
    right = base_x + track_w // 2
    # Track outline: flat top + flat bottom + half-circles on ends.
    r = track_h // 2
    pygame.draw.rect(surface, C.PAPER, (left + r, track_top, track_w - 2 * r, track_h))
    pygame.draw.circle(surface, C.PAPER, (left + r, track_top + r), r)
    pygame.draw.circle(surface, C.PAPER, (right - r, track_top + r), r)
    # Outline (two straight segments + two arcs).
    R.sketch_line(surface, C.INK, (left + r, track_top), (right - r, track_top),
                  width=C.LINE_WIDTH_MEDIUM, seed=71)
    R.sketch_line(surface, C.INK, (left + r, track_bottom), (right - r, track_bottom),
                  width=C.LINE_WIDTH_MEDIUM, seed=72)
    pygame.draw.arc(surface, C.INK,
                    (left, track_top, 2 * r, track_h), math.pi / 2, 3 * math.pi / 2, 3)
    pygame.draw.arc(surface, C.INK,
                    (right - 2 * r, track_top, 2 * r, track_h), -math.pi / 2, math.pi / 2, 3)

    # Track tread teeth (diagonal slashes along the top + bottom edges).
    for x in range(left + r + 6, right - r - 6, 14):
        pygame.draw.line(surface, C.INK, (x, track_top + 3), (x + 8, track_top + 10), 2)
        pygame.draw.line(surface, C.INK, (x, track_bottom - 10), (x + 8, track_bottom - 3), 2)

    # Road wheels inside the track belt — each shows a spoke line that rotates
    # with the robot's driving state.
    wheel_y = track_top + r
    wheel_rad = r - 8
    for wheel_x in range(left + r, right - r + 1, (track_w - 2 * r) // 4):
        pygame.draw.circle(surface, C.PAPER, (wheel_x, wheel_y), wheel_rad)
        pygame.draw.circle(surface, C.INK, (wheel_x, wheel_y), wheel_rad, 2)
        # Spoke line
        sx = wheel_x + wheel_rad * math.cos(wheel_rot)
        sy = wheel_y + wheel_rad * math.sin(wheel_rot)
        pygame.draw.line(surface, C.INK,
                         (wheel_x - (sx - wheel_x), wheel_y - (sy - wheel_y)),
                         (sx, sy), 2)
        pygame.draw.circle(surface, C.INK_SOFT, (wheel_x, wheel_y), 2)
    # Drive sprockets (bigger wheels at each end, with a toothed outline).
    for sprocket_x in (left + r, right - r):
        sprocket_rad = r - 5
        pygame.draw.circle(surface, C.PAPER, (sprocket_x, wheel_y), sprocket_rad)
        # Toothed ring (8 teeth rotating with wheel_rot)
        for k in range(8):
            theta = wheel_rot + k * math.pi / 4
            tx = sprocket_x + sprocket_rad * math.cos(theta)
            ty = wheel_y + sprocket_rad * math.sin(theta)
            tox = sprocket_x + (sprocket_rad + 4) * math.cos(theta)
            toy = wheel_y + (sprocket_rad + 4) * math.sin(theta)
            pygame.draw.line(surface, C.INK, (tx, ty), (tox, toy), 2)
        R.sketch_circle(surface, fill=None, outline=C.INK,
                        center=(sprocket_x, wheel_y), radius=sprocket_rad,
                        width=2, seed=80 + sprocket_x)
        pygame.draw.circle(surface, C.ACCENT, (sprocket_x, wheel_y), 4)

    # --- Chassis (box above tracks) ---
    chassis_w = 140
    chassis_h = 40
    chassis_top = track_top - chassis_h
    chassis_rect = pygame.Rect(base_x - chassis_w // 2, chassis_top, chassis_w, chassis_h)
    pygame.draw.rect(surface, C.PAPER, chassis_rect)
    R.sketch_polyline(surface, C.INK, [
        (chassis_rect.left, chassis_rect.bottom),
        (chassis_rect.left, chassis_rect.top),
        (chassis_rect.right, chassis_rect.top),
        (chassis_rect.right, chassis_rect.bottom),
    ], width=C.LINE_WIDTH_MEDIUM, seed=73)
    # Chassis panel seam
    R.sketch_line(surface, C.INK_SOFT,
                  (chassis_rect.left + 10, chassis_rect.centery),
                  (chassis_rect.right - 10, chassis_rect.centery),
                  width=2, seed=74)
    # Nameplate on chassis
    R.text(surface, "NEWT-3 · TREADED", (base_x, chassis_rect.centery),
           size=C.SIZE_SMALL, color=C.INK_SOFT,
           font_path=C.FONT_HEADING, anchor="center")

    # --- Turret (dome between chassis and shoulder) ---
    turret_r = 28
    turret_cy = chassis_top - turret_r + 6
    # Draw the full disc so the base of it is flush with the chassis top.
    pygame.draw.circle(surface, C.PAPER, (base_x, turret_cy + turret_r), turret_r, 0)
    pygame.draw.rect(surface, C.PAPER,
                     (base_x - turret_r, turret_cy + turret_r - 2, turret_r * 2, 4))
    # Dome arc.
    pygame.draw.arc(surface, C.INK,
                    (base_x - turret_r, turret_cy, turret_r * 2, turret_r * 2),
                    0, math.pi, 3)
    # Horizontal seam line where dome meets chassis.
    R.sketch_line(surface, C.INK,
                  (base_x - turret_r, turret_cy + turret_r),
                  (base_x + turret_r, turret_cy + turret_r),
                  width=C.LINE_WIDTH_MEDIUM, seed=75)

    # Headlights / sensors on top of the chassis, either side of the turret.
    for side in (-1, +1):
        lx = base_x + side * (turret_r + 22)
        ly = chassis_top + 8
        pygame.draw.circle(surface, C.ACCENT, (lx, ly), 5)
        pygame.draw.circle(surface, C.INK, (lx, ly), 5, 2)

    # Shoulder collar — short vertical riser from turret apex to arm joint.
    if top_y < turret_cy:
        riser_top = top_y
        R.sketch_polyline(surface, C.INK, [
            (base_x - 10, turret_cy + 2), (base_x - 10, riser_top + 6),
            (base_x + 10, riser_top + 6), (base_x + 10, turret_cy + 2),
        ], width=C.LINE_WIDTH_MEDIUM, seed=76)


def _draw_motor(
    surface: pygame.Surface,
    center: tuple[float, float],
    radius: int,
    label: str | None = None,
    active: bool = True,
    seed: int = 0,
) -> None:
    """Servo motor icon: shell + inner shaft cross + optional status LED."""
    fill = C.PAPER
    R.sketch_circle(surface, fill=fill, outline=C.INK, center=center,
                    radius=radius, width=C.LINE_WIDTH_MEDIUM, seed=seed)
    # Inner shaft circle
    R.sketch_circle(surface, fill=None, outline=C.INK_SOFT,
                    center=center, radius=max(3, radius // 3),
                    width=2, seed=seed + 1)
    # Cross for the axis mark
    cx, cy = center
    inner = max(3, radius // 3)
    pygame.draw.line(surface, C.INK, (cx - inner, cy), (cx + inner, cy), 2)
    pygame.draw.line(surface, C.INK, (cx, cy - inner), (cx, cy + inner), 2)
    # Status LED
    led_color = C.GREEN if active else C.INK_SOFT
    led = (int(cx + radius * 0.6), int(cy - radius * 0.6))
    pygame.draw.circle(surface, led_color, led, 3)
    pygame.draw.circle(surface, C.INK, led, 3, 1)
    # Label
    if label is not None:
        R.text(surface, label, (cx, cy + radius + 14), size=C.SIZE_SMALL,
               color=C.INK_SOFT, font_path=C.FONT_HEADING, anchor="center")


def _draw_gripper(
    surface: pygame.Surface,
    ee_xz: tuple[float, float],
    angle_world: float,
    open_fraction: float,
) -> None:
    """Two-finger parallel gripper at the end effector.

    Dramatically animated: splayed wide when idle, clamped tight when holding.
    `open_fraction` 0..1. Fingers are anchored at the wrist and project forward
    past the end-effector point so the tip of the hand link is visibly inside
    the jaws.
    """
    ex_px, ey_px = world_to_screen(*ee_xz)
    # Hand direction in world frame (same angle as last link).
    angle_screen = -angle_world
    fwd = (math.cos(angle_screen), math.sin(angle_screen))
    perp = (-fwd[1], fwd[0])

    # Wrist flange (rotated rectangle perpendicular to fwd, straddling the EE).
    flange_len = 10
    flange_w = 28
    corners = []
    for dl, dw in [(-flange_len, -flange_w), (-flange_len, flange_w),
                   (flange_len, flange_w), (flange_len, -flange_w)]:
        corners.append((ex_px + fwd[0] * dl + perp[0] * dw,
                        ey_px + fwd[1] * dl + perp[1] * dw))
    pygame.draw.polygon(surface, C.PAPER, corners)
    R.sketch_polyline(surface, C.INK, corners + [corners[0]],
                      width=C.LINE_WIDTH_MEDIUM, seed=310)
    # Bolt dots on the flange.
    for side in (-1, +1):
        bx = ex_px + perp[0] * side * flange_w * 0.6
        by = ey_px + perp[1] * side * flange_w * 0.6
        pygame.draw.circle(surface, C.INK, (int(bx), int(by)), 2)

    # Finger geometry. When closed, the fingers sit JUST OUTSIDE the block
    # (block half-width = BLOCK_HALF * PX_PER_M = 18 px), so the audience
    # sees the jaws clearly pinching the block from both sides. When open,
    # the gap is wide enough to be unambiguously "ungripping".
    from .physics import BLOCK_HALF
    block_half_px = BLOCK_HALF * C.PX_PER_M
    gap_closed = block_half_px + 6                  # just past the block edge
    gap_open = block_half_px + 32                   # comfortably wider
    gap = gap_closed + open_fraction * (gap_open - gap_closed)
    finger_len = 60
    hook_len = 14
    # Fingers turn ACCENT orange when actively clamped (pinching) — draws the
    # eye to the moment of grasp. Idle/open is drawn in the neutral ink color.
    status_color = C.ACCENT if open_fraction < 0.3 else C.INK
    finger_width = C.LINE_WIDTH_THICK + 2

    for side in (+1, -1):
        # Root at the flange edge, offset by half-gap perpendicular.
        root = (ex_px + fwd[0] * flange_len + perp[0] * side * gap,
                ey_px + fwd[1] * flange_len + perp[1] * side * gap)
        tip = (root[0] + fwd[0] * finger_len,
               root[1] + fwd[1] * finger_len)
        # Inward hook at the tip (the "fingertip").
        hook = (tip[0] - perp[0] * side * hook_len,
                tip[1] - perp[1] * side * hook_len)
        R.sketch_polyline(surface, status_color, [root, tip, hook],
                          width=finger_width, seed=320 + side)
        # Gripping pad on the inside surface (rectangle).
        pad_t = 0.55
        pad_center = (root[0] + fwd[0] * finger_len * pad_t,
                      root[1] + fwd[1] * finger_len * pad_t)
        pad_dx, pad_dy = -perp[0] * side * 3, -perp[1] * side * 3
        pad_a = (pad_center[0] - fwd[0] * 8 + pad_dx, pad_center[1] - fwd[1] * 8 + pad_dy)
        pad_b = (pad_center[0] + fwd[0] * 8 + pad_dx, pad_center[1] + fwd[1] * 8 + pad_dy)
        pygame.draw.line(surface, C.ACCENT, pad_a, pad_b, 4)


def _update_gripper_state(target_open: float, dt: float, state: dict) -> float:
    """Smooth the open/close with a second-order critically damped spring so
    the jaws glide rather than snap — matches the silky feel of the arm."""
    current = state.get("open", 1.0)
    velocity = state.get("open_vel", 0.0)
    # Critically damped spring: natural freq ω, damping ratio 1.
    omega = 9.0
    accel = (target_open - current) * omega * omega - 2 * omega * velocity
    velocity = velocity + accel * dt
    current = current + velocity * dt
    # Clamp to avoid overshoot artifacts.
    current = max(-0.05, min(1.05, current))
    state["open"] = current
    state["open_vel"] = velocity
    return current


# Module-level animation state for the gripper. Holds a low-pass on the
# hand-link's angle so tiny PD oscillations don't translate into gripper
# shake — the jaws move smoothly even when the underlying body jitters.
_GRIPPER_STATE: dict = {"open": 1.0, "hand_angle": 0.0}


def draw_arm(
    surface: pygame.Surface,
    world: World,
    holding: bool = False,
    frame_dt: float = 1 / 60,
) -> None:
    """Robot arm: structural links, servo motors, and a two-finger gripper.

    Rendered from the controller's commanded pose (forward-kinematics of the
    joint target), not the noisy physics body_q — this keeps the arm visually
    steady even when the XPBD solver oscillates a few millimetres around the
    set-point. Screen Y flips relative to world Z, so rotation angles negate.

    `holding=True` closes the gripper around a carried block. The state is
    smoothed per-frame so the transition is visible to the audience.
    """
    st = world.arm_state_from_target()
    base_offset = world.base_x

    # Link colors: primary → secondary gradient.
    # Each link is rendered as a CAPSULE: central rectangle plus a filled
    # circle at each end — those circles are what make the joints "glue"
    # together visually, regardless of the bend angle.
    for i, (pose, length) in enumerate(zip(st.link_poses, world.link_lengths, strict=True)):
        cx_px, cy_px = local_to_screen(*pose.center_xz, base_offset)
        screen_angle = -pose.angle
        cos_a, sin_a = math.cos(screen_angle), math.sin(screen_angle)
        t = i / (len(world.link_lengths) - 1) if len(world.link_lengths) > 1 else 0
        fill = tuple(int(C.PRIMARY[j] * (1 - t) + C.SECONDARY[j] * t) for j in range(3))
        half_w_px = (length * C.PX_PER_M) / 2
        half_h_px = LINK_HALF_W * C.PX_PER_M * 1.7
        cap_r = int(half_h_px + 2)

        # Capsule end caps (drawn first so the rectangle outline sits on top)
        end_local_a = (-half_w_px, 0)
        end_local_b = (+half_w_px, 0)
        ax = cx_px + cos_a * end_local_a[0] - sin_a * end_local_a[1]
        ay = cy_px + sin_a * end_local_a[0] + cos_a * end_local_a[1]
        bx = cx_px + cos_a * end_local_b[0] - sin_a * end_local_b[1]
        by = cy_px + sin_a * end_local_b[0] + cos_a * end_local_b[1]
        pygame.draw.circle(surface, fill, (int(ax), int(ay)), cap_r)
        pygame.draw.circle(surface, fill, (int(bx), int(by)), cap_r)

        R.sketch_rect(
            surface,
            fill=fill,
            outline=C.INK,
            center=(cx_px, cy_px),
            half_w=half_w_px,
            half_h=half_h_px,
            angle=screen_angle,
            width=C.LINE_WIDTH_THICK,
            seed=100 + i,
        )

        # Panel lines along the link for structural detail.
        panel_offset = half_h_px * 0.45
        for side in (+1, -1):
            a_local = (-half_w_px * 0.75, panel_offset * side)
            b_local = (half_w_px * 0.75, panel_offset * side)
            a = (cx_px + cos_a * a_local[0] - sin_a * a_local[1],
                 cy_px + sin_a * a_local[0] + cos_a * a_local[1])
            b = (cx_px + cos_a * b_local[0] - sin_a * b_local[1],
                 cy_px + sin_a * b_local[0] + cos_a * b_local[1])
            R.sketch_line(surface, C.INK_SOFT, a, b, width=2, wobble=0.4, seed=150 + i * 10 + side)

    # Joints as labeled servo motors — sized so they always overlap the
    # adjacent link capsule caps, hiding any sub-pixel seam.
    ends_px = [local_to_screen(x, z, base_offset) for x, z in st.link_world_ends]
    link_half_h = LINK_HALF_W * C.PX_PER_M * 1.7
    motor_radius = int(link_half_h + 8)
    joint_labels = ["J1", "J2", "J3"]
    for i, pt in enumerate(ends_px[:-1]):   # skip EE
        _draw_motor(surface, pt, radius=motor_radius, label=joint_labels[i],
                    active=True, seed=200 + i)

    # Gripper at the end effector. Because the arm is FK-rendered from the
    # controller target (already smooth), no extra low-pass is needed on
    # the hand angle — use it directly for responsive catch poses.
    hand_angle = st.link_poses[-1].angle if st.link_poses else 0.0

    target_open = 0.0 if holding else 1.0
    open_fraction = _update_gripper_state(target_open, frame_dt, _GRIPPER_STATE)
    ee_world = (st.end_effector[0] + base_offset, st.end_effector[1])
    _draw_gripper(surface, ee_world, hand_angle, open_fraction)


def draw_ball(surface: pygame.Surface, world: World) -> None:
    """Render the catcher ball (only if it's inside the viewport)."""
    (x, z), _ = world.ball_state()
    if x > 3.5 or x < -3.0 or z > 3.0 or z < -0.5:
        return
    cx, cy = world_to_screen(x, z)
    radius_px = int(world.ball.radius * C.PX_PER_M)
    R.sketch_circle(
        surface,
        fill=C.ACCENT,
        outline=C.INK,
        center=(cx, cy),
        radius=radius_px,
        width=C.LINE_WIDTH_MEDIUM,
        seed=1234,
    )


def draw_trajectory(
    surface: pygame.Surface,
    world: World,
    horizon: float = 1.5,
    dt: float = 0.05,
) -> None:
    """Dashed predicted ballistic trajectory from the ball's current state."""
    (x, z), (vx, vz) = world.ball_state()
    if z < 0.15 or vz < -12 or abs(vx) < 0.01:
        return
    g = 9.81
    steps = int(horizon / dt)
    prev = world_to_screen(x, z)
    for i in range(1, steps + 1):
        t = i * dt
        xi = x + vx * t
        zi = z + vz * t - 0.5 * g * t * t
        if zi < 0.05:
            break
        curr = world_to_screen(xi, zi)
        if i % 2 == 0:     # dashed
            pygame.draw.line(surface, C.INK_SOFT, prev, curr, 2)
        prev = curr


def draw_launch_preview(
    surface: pygame.Surface,
    start_world: tuple[float, float],
    velocity_world: tuple[float, float],
) -> None:
    """Ghost ball at the launch point + an arrow showing the current velocity,
    plus a dashed parabolic trajectory forecasting where the ball will fly.
    Audience sees exactly what they're about to throw before releasing."""
    GRAVITY = 9.81
    x0, z0 = start_world
    vx, vz = velocity_world

    # Dashed trajectory preview, up to 1.2s or ground strike.
    prev = world_to_screen(x0, z0)
    t = 0.0
    dt = 0.05
    for i in range(1, 28):
        t = i * dt
        xi = x0 + vx * t
        zi = z0 + vz * t - 0.5 * GRAVITY * t * t
        if zi < 0.05:
            break
        curr = world_to_screen(xi, zi)
        if i % 2 == 0:
            pygame.draw.line(surface, C.ACCENT, prev, curr, 2)
        prev = curr

    # Ghost ball
    cx, cy = world_to_screen(x0, z0)
    R.sketch_circle(surface, fill=None, outline=C.ACCENT,
                    center=(cx, cy), radius=12,
                    width=C.LINE_WIDTH_MEDIUM, seed=8881)

    # Velocity arrow — 1 m/s = 18 px (tenth of PX_PER_M)
    scale = 18
    ax, ay = cx, cy
    bx = cx + int(vx * scale)
    by = cy - int(vz * scale)
    pygame.draw.line(surface, C.ACCENT, (ax, ay), (bx, by), 4)
    # Arrow head
    import math as _m
    ang = _m.atan2(by - ay, bx - ax)
    for ha in (ang + 2.6, ang - 2.6):
        hx = bx + int(12 * _m.cos(ha))
        hy = by + int(12 * _m.sin(ha))
        pygame.draw.line(surface, C.ACCENT, (bx, by), (hx, hy), 3)


def draw_intercept_marker(
    surface: pygame.Surface,
    xz: tuple[float, float] | None,
) -> None:
    if xz is None:
        return
    cx, cy = world_to_screen(*xz)
    R.sketch_circle(
        surface,
        fill=None,
        outline=C.ACCENT,
        center=(cx, cy),
        radius=22,
        width=3,
        seed=4444,
    )
    pygame.draw.line(surface, C.ACCENT, (cx - 14, cy), (cx + 14, cy), 2)
    pygame.draw.line(surface, C.ACCENT, (cx, cy - 14), (cx, cy + 14), 2)


def draw_blocks(surface: pygame.Surface, world: World) -> None:
    for block, (x, z), rot in world.block_poses():
        cx, cy = world_to_screen(x, z)
        half_px = BLOCK_HALF * C.PX_PER_M
        color = C.BLOCK_COLORS.get(block.color, C.INK_SOFT)
        R.sketch_rect(
            surface,
            fill=color,
            outline=C.INK,
            center=(cx, cy),
            half_w=half_px,
            half_h=half_px,
            angle=-rot,   # rot is around Y; screen Y is flipped, so negate
            width=C.LINE_WIDTH_MEDIUM,
            seed=hash(block.color) & 0xFFFF,
        )


# ------------------------------------------------------------------ chrome

def draw_header(surface: pygame.Surface, mode_label: str, fps: float) -> None:
    R.sketch_line(surface, C.INK, (0, C.HEADER_HEIGHT),
                  (C.WIDTH, C.HEADER_HEIGHT),
                  width=C.LINE_WIDTH_MEDIUM, wobble=0.2, seed=501)
    R.text(surface, "NEWTON EMBODIED AI", (40, 26), size=C.SIZE_H1,
           color=C.INK, font_path=C.FONT_HEADING)
    R.text(surface, "Live Classroom Demo", (40, 72), size=C.SIZE_BODY,
           color=C.INK_SOFT, font_path=C.FONT_BODY)

    # Right side: mode + fps
    R.text(surface, f"MODE  {mode_label}", (C.WIDTH - 40, 30),
           size=C.SIZE_H2, color=C.PRIMARY,
           font_path=C.FONT_HEADING, anchor="tr")
    R.text(surface, f"{fps:5.1f} fps", (C.WIDTH - 40, 72),
           size=C.SIZE_SMALL, color=C.INK_SOFT,
           font_path=C.FONT_BODY, anchor="tr")


def draw_side_panel(
    surface: pygame.Surface,
    status_lines: list[str],
    recent_commands: list[str] | None = None,
    parsed_json: dict | None = None,
) -> None:
    x0 = C.VIEWPORT_WIDTH
    # Vertical divider
    R.sketch_line(surface, C.INK, (x0, C.HEADER_HEIGHT),
                  (x0, C.HEIGHT - C.FOOTER_HEIGHT),
                  width=C.LINE_WIDTH_MEDIUM, wobble=0.2, seed=601)

    # Title
    R.text(surface, "CONTROLS", (x0 + 30, C.HEADER_HEIGHT + 20),
           size=C.SIZE_H2, color=C.PRIMARY, font_path=C.FONT_HEADING)

    # Key bindings
    bindings = [
        ("1", "Ball catch  (MPC)"),
        ("2", "Type command (VLA)"),
        ("3", "Speak command"),
        ("R", "Reset scene"),
        ("Q", "Quit"),
    ]
    y = C.HEADER_HEIGHT + 80
    for key, desc in bindings:
        # Key chip
        chip = pygame.Rect(x0 + 30, y, 44, 44)
        pygame.draw.rect(surface, C.PAPER, chip)
        R.sketch_polyline(surface, C.INK, [
            (chip.left, chip.top),
            (chip.right, chip.top),
            (chip.right, chip.bottom),
            (chip.left, chip.bottom),
            (chip.left, chip.top),
        ], width=3, seed=hash(key) & 0xFFFF)
        R.text(surface, key, chip.center, size=C.SIZE_LARGE,
               color=C.INK, font_path=C.FONT_HEADING, anchor="center")
        R.text(surface, desc, (x0 + 90, y + 8), size=C.SIZE_BODY,
               color=C.INK, font_path=C.FONT_BODY)
        y += 60

    # AI Thinking (JSON) section — show the LLM-parsed action so the audience
    # sees the natural-language → structured-action translation. Up to 7
    # fields so user/via/latency stay visible alongside action/color/reason.
    if parsed_json is not None:
        R.sketch_line(surface, C.INK_SOFT,
                      (x0 + 30, y + 10), (C.WIDTH - 30, y + 10),
                      width=2, wobble=0.2, seed=702)
        R.text(surface, "AI  THINKING", (x0 + 30, y + 30),
               size=C.SIZE_SMALL, color=C.PRIMARY,
               font_path=C.FONT_HEADING)
        lines = [f"  {k}: {v}" for k, v in parsed_json.items() if v is not None]
        yy = y + 58
        for line in lines[:7]:
            R.text(surface, line[:42], (x0 + 30, yy),
                   size=C.SIZE_SMALL, color=C.INK_SOFT,
                   font_path=C.FONT_BODY)
            yy += 22
        y = yy + 6

    # Recent commands.
    if recent_commands:
        R.sketch_line(surface, C.INK_SOFT,
                      (x0 + 30, y + 10), (C.WIDTH - 30, y + 10),
                      width=2, wobble=0.2, seed=703)
        R.text(surface, "RECENT", (x0 + 30, y + 30),
               size=C.SIZE_SMALL, color=C.INK_SOFT,
               font_path=C.FONT_HEADING)
        yy = y + 58
        for line in recent_commands[-3:]:
            R.text(surface, f'"  {line[:26]}  "', (x0 + 30, yy),
                   size=C.SIZE_SMALL, color=C.INK, font_path=C.FONT_BODY)
            yy += 22
        y = yy + 6

    # Status / log.
    R.sketch_line(surface, C.INK_SOFT,
                  (x0 + 30, y + 10), (C.WIDTH - 30, y + 10),
                  width=2, wobble=0.2, seed=701)
    R.text(surface, "STATUS", (x0 + 30, y + 30),
           size=C.SIZE_SMALL, color=C.INK_SOFT,
           font_path=C.FONT_HEADING)
    yy = y + 60
    # Reduced to 6 lines to make room for new sections.
    for line in status_lines[-6:]:
        R.text(surface, line[:40], (x0 + 30, yy), size=C.SIZE_BODY,
               color=C.INK, font_path=C.FONT_BODY)
        yy += 26


def draw_footer(
    surface: pygame.Surface,
    prompt: str,
    input_text: str,
    input_active: bool,
    thinking: bool = False,
    listening: bool = False,
) -> None:
    y0 = C.HEIGHT - C.FOOTER_HEIGHT
    R.sketch_line(surface, C.INK, (0, y0), (C.WIDTH, y0),
                  width=C.LINE_WIDTH_MEDIUM, wobble=0.2, seed=801)

    # Prompt label
    R.text(surface, prompt, (40, y0 + 20), size=C.SIZE_BODY,
           color=C.INK_SOFT, font_path=C.FONT_BODY)

    # Input box
    box = pygame.Rect(40, y0 + 50, C.WIDTH - 80, 52)
    pygame.draw.rect(surface, C.PAPER, box)
    color = C.ACCENT if thinking else (C.PRIMARY if input_active else C.INK_SOFT)
    R.sketch_polyline(
        surface,
        color,
        [
            (box.left, box.top),
            (box.right, box.top),
            (box.right, box.bottom),
            (box.left, box.bottom),
            (box.left, box.top),
        ],
        width=C.LINE_WIDTH_MEDIUM,
        seed=901,
    )

    if listening:
        # Mic icon + animated waveform.
        t = pygame.time.get_ticks() / 120
        label_y = box.y + 10
        # Mic circle
        mic_x = box.x + 40
        mic_y = box.centery
        pygame.draw.circle(surface, C.ACCENT, (mic_x, mic_y), 14)
        pygame.draw.circle(surface, C.INK, (mic_x, mic_y), 14, 2)
        pygame.draw.line(surface, C.INK,
                         (mic_x - 6, mic_y - 2),
                         (mic_x - 6, mic_y + 4), 3)
        pygame.draw.line(surface, C.INK,
                         (mic_x + 6, mic_y - 2),
                         (mic_x + 6, mic_y + 4), 3)
        # Bouncing waveform bars
        for i in range(18):
            bar_x = box.x + 80 + i * 18
            amp = 8 + 14 * abs(math.sin(t + i * 0.4))
            pygame.draw.line(surface, C.ACCENT, (bar_x, box.centery - amp),
                             (bar_x, box.centery + amp), 4)
        R.text(surface, "Listening…", (box.right - 160, label_y),
               size=C.SIZE_LARGE, color=C.ACCENT, font_path=C.FONT_ACCENT)
    elif thinking:
        # Animated "Thinking" with pulsing dots.
        dots = 1 + (pygame.time.get_ticks() // 300) % 3
        label = "Thinking" + "." * dots
        R.text(surface, label, (box.x + 20, box.y + 10),
               size=C.SIZE_LARGE, color=C.ACCENT,
               font_path=C.FONT_ACCENT)
    else:
        cursor = "_" if input_active and (pygame.time.get_ticks() // 500) % 2 == 0 else ""
        R.text(surface, f"> {input_text}{cursor}", (box.x + 20, box.y + 10),
               size=C.SIZE_LARGE, color=C.INK,
               font_path=C.FONT_ACCENT)
