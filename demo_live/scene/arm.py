"""Arm pedestal, mobile base, links + gripper, and the per-frame arm render.

These are the heaviest single set of drawables — separated from the rest
of the workspace to keep each scene module under the 800-line ceiling.
"""

from __future__ import annotations

import contextlib
import math

import pygame

from .. import config as C
from .. import render as R
from ..physics import BLOCK_HALF, LINK_HALF_W, World, local_to_screen, world_to_screen


def draw_arm_pedestal(surface: pygame.Surface, anchor_world_x: float) -> None:
    """Industrial control cabinet + slim mounting column for the secondary
    FK-only arm. Reads as a fixed UR-class workstation: heavy cabinet at
    the floor (vents + status display + manufacturer placard), a thin
    machined column rising to the J1 mount, cable conduit on the front
    face, anchor plate with visible bolts on the floor.
    """
    base_x_px, base_y_px = local_to_screen(0.0, 0.0, anchor_world_x)
    top_x_px, top_y_px = local_to_screen(0.0, C.ARM_BASE_Z, anchor_world_x)

    # --- Floor anchor plate (visible bolts) ---
    plate_w = 130
    plate_h = 10
    plate_left = base_x_px - plate_w // 2
    plate_top = base_y_px - plate_h
    # Contact shadow grounding the fixed cabinet (behind the anchor plate).
    R.ground_shadow(surface, base_x_px, base_y_px, rx=int(plate_w * 0.7), ry=11, strength=1.1)
    pygame.draw.rect(surface, C.UR_BODY_SHADOW,
                     (plate_left, plate_top, plate_w, plate_h))
    pygame.draw.rect(surface, C.UR_BODY_OUTLINE,
                     (plate_left, plate_top, plate_w, plate_h), 1)
    for dx in (12, plate_w - 12):
        pygame.draw.circle(surface, C.UR_BOLT,
                           (plate_left + dx, plate_top + plate_h // 2), 3)

    # --- Control cabinet (heavy white box at the floor) ---
    cab_w = 96
    cab_h = 110
    cab_left = base_x_px - cab_w // 2
    cab_bot = plate_top
    cab_top = cab_bot - cab_h
    R.aa_rounded_rect(surface,
                      fill=C.UR_BODY, outline=C.UR_BODY_OUTLINE,
                      rect=(cab_left, cab_top, cab_w, cab_h),
                      radius=6, width=2)
    # Cabinet shadow band on the lower portion.
    pygame.draw.rect(surface, C.UR_BODY_SHADOW,
                     (cab_left + 3, cab_top + int(cab_h * 0.7),
                      cab_w - 6, int(cab_h * 0.27)))
    # Vent louvers (5 horizontal lines on the upper-left of the cabinet).
    vent_x = cab_left + 12
    for k in range(5):
        ly = cab_top + 14 + k * 8
        pygame.draw.line(surface, C.UR_BODY_OUTLINE,
                         (vent_x, ly), (vent_x + 26, ly), 2)
    # Status display window (small dark rect with cyan dot for "armed").
    disp_x = cab_left + cab_w - 36
    disp_y = cab_top + 14
    pygame.draw.rect(surface, C.UR_JOINT_HOUSING,
                     (disp_x, disp_y, 28, 16))
    pygame.draw.rect(surface, C.UR_BOLT,
                     (disp_x, disp_y, 28, 16), 1)
    # Pulsing cyan dot inside the display.
    now_ms = pygame.time.get_ticks() / 1000.0
    p = 0.5 + 0.5 * math.sin(2 * math.pi * now_ms / 1.6)
    dot_r = max(2, int(4 * p))
    pygame.draw.circle(surface, C.UR_ACCENT,
                       (disp_x + 7, disp_y + 8), dot_r)
    # Cabinet door handle (small horizontal bar).
    pygame.draw.line(surface, C.UR_BOLT,
                     (cab_left + cab_w - 18, cab_top + cab_h - 22),
                     (cab_left + cab_w - 6, cab_top + cab_h - 22), 3)
    # Manufacturer placard etched into the door.
    R.text(surface, "ARM-B / FIXED",
           (base_x_px, cab_top + cab_h - 12),
           size=C.SIZE_SMALL, color=C.INDUSTRIAL_INK_SOFT,
           font_path=C.FONT_HEADING, anchor="center")

    # --- Slim machined column from cabinet top to J1 mount ---
    col_w = 26
    col_left = base_x_px - col_w // 2
    col_top = top_y_px + 4
    col_bot = cab_top
    pygame.draw.rect(surface, C.UR_BODY,
                     (col_left, col_top, col_w, col_bot - col_top))
    pygame.draw.rect(surface, C.UR_BODY_OUTLINE,
                     (col_left, col_top, col_w, col_bot - col_top), 2)
    # Cylindrical shadow stripe on the right side of the column.
    shadow_w = 7
    pygame.draw.rect(surface, C.UR_BODY_SHADOW,
                     (col_left + col_w - shadow_w - 1, col_top + 2,
                      shadow_w, col_bot - col_top - 4))
    # Cable conduit running up the front of the column (offset to the left).
    conduit_x = base_x_px - col_w // 2 + 5
    pygame.draw.rect(surface, C.UR_CABLE,
                     (conduit_x - 2, col_top + 6, 4, col_bot - col_top - 12))
    # Bolt rosette at the column-cabinet junction.
    for dx in (col_left + 4, col_left + col_w - 4):
        pygame.draw.circle(surface, C.UR_BOLT, (dx, col_bot - 4), 2)


def draw_arm_base(
    surface: pygame.Surface,
    world: World | None = None,
    mode_label: str = "IDLE",
    thinking: bool = False,
) -> None:
    """Tracked (tank-style) mobile robot base. Spins wheels when driving.

    `mode_label` colors the chassis sensor LEDs to match the current
    interaction state (idle / listening / talking / executing).
    `thinking=True` adds a rotating radar arc around the turret for the
    span of an active VLA parse, so the audience can see "AI is working".
    """
    base_offset = world.base_x if world is not None else 0.0
    wheel_rot = world.track_rotation if world is not None else 0.0
    base_x, base_y = local_to_screen(0.0, 0.0, base_offset)
    top_x, top_y = local_to_screen(0.0, C.ARM_BASE_Z, base_offset)
    now_ms = pygame.time.get_ticks() / 1000.0

    # --- AGV chassis (rounded body, white) ---
    chassis_w = 220
    chassis_h = 92
    chassis_left = base_x - chassis_w // 2
    chassis_top = base_y - chassis_h
    # Broad contact shadow grounding the mobile base (drawn first, behind body).
    R.ground_shadow(surface, base_x, base_y, rx=int(chassis_w * 0.55), ry=14, strength=1.2)
    R.aa_rounded_rect(surface,
                      fill=C.UR_BODY, outline=C.UR_BODY_OUTLINE,
                      rect=(chassis_left, chassis_top, chassis_w, chassis_h),
                      radius=14, width=2)
    # Cylindrical shadow band along the lower 35%.
    shadow_top = chassis_top + int(chassis_h * 0.65)
    pygame.draw.rect(surface, C.UR_BODY_SHADOW,
                     (chassis_left + 4, shadow_top,
                      chassis_w - 8, chassis_h - (shadow_top - chassis_top) - 4))

    # --- Wheel arches + omni-wheels visible underneath ---
    arch_y = base_y - 4
    arch_r = 26
    wheel_offsets = (-chassis_w // 4, +chassis_w // 4)
    for off in wheel_offsets:
        wx = base_x + off
        # Tight dark contact patch under each wheel (reads as bearing load).
        R.ground_shadow(surface, wx, base_y, rx=int(arch_r * 0.8), ry=5, strength=1.6)
        # Wheel arch cut-out (drawn over chassis to suggest a fender).
        pygame.draw.rect(surface, C.UR_BODY_SHADOW,
                         (wx - arch_r, arch_y - arch_r,
                          arch_r * 2, arch_r))
        pygame.draw.arc(surface, C.UR_BODY_OUTLINE,
                        (wx - arch_r, arch_y - arch_r,
                         arch_r * 2, arch_r * 2),
                        math.pi, 2 * math.pi, 2)
        # Omni-wheel: dark tyre + lighter hub + 6 segment lines that rotate.
        R.aa_circle(surface, fill=C.UR_JOINT_HOUSING, outline=C.UR_BOLT,
                    center=(wx, arch_y - 4), radius=arch_r - 8, width=1)
        R.aa_circle(surface, fill=C.UR_JOINT_FACE, outline=C.UR_BOLT,
                    center=(wx, arch_y - 4), radius=arch_r - 14, width=1)
        # Rolling spokes (6 segments, phased on wheel_rot).
        for k in range(6):
            theta = wheel_rot + k * math.pi / 3
            sx = wx + (arch_r - 9) * math.cos(theta)
            sy = (arch_y - 4) + (arch_r - 9) * math.sin(theta)
            pygame.draw.line(surface, C.UR_BOLT,
                             (wx, arch_y - 4), (int(sx), int(sy)), 2)
        # UR cyan hub dot, with a soft powered bloom.
        R.aa_glow_dot(surface, wx, arch_y - 4, 3)
        pygame.draw.circle(surface, C.UR_ACCENT, (wx, arch_y - 4), 3)

    # --- Side vent louvers on the left fender ---
    vent_x = chassis_left + 14
    for k in range(4):
        ly = chassis_top + 24 + k * 11
        pygame.draw.line(surface, C.UR_BODY_OUTLINE,
                         (vent_x, ly), (vent_x + 22, ly), 2)
    # E-STOP mushroom button (red dot inside black ring) on the right side.
    estop_x = chassis_left + chassis_w - 24
    estop_y = chassis_top + 28
    pygame.draw.circle(surface, C.UR_JOINT_HOUSING, (estop_x, estop_y), 9)
    pygame.draw.circle(surface, C.LED_RED, (estop_x, estop_y), 6)
    pygame.draw.circle(surface, C.UR_BOLT, (estop_x, estop_y), 9, 1)

    # --- Manufacturer placard ---
    R.text(surface, "NEWT-3 / UR-class",
           (base_x, chassis_top + 14),
           size=C.SIZE_SMALL, color=C.INDUSTRIAL_INK_SOFT,
           font_path=C.FONT_HEADING, anchor="center")

    # --- Lidar dome on top of the chassis ---
    lidar_cx = base_x - 50
    lidar_cy = chassis_top - 2
    lidar_r = 14
    pygame.draw.circle(surface, C.UR_JOINT_HOUSING,
                       (lidar_cx, lidar_cy + lidar_r // 2), lidar_r, 0)
    pygame.draw.rect(surface, C.UR_JOINT_HOUSING,
                     (lidar_cx - lidar_r, lidar_cy + lidar_r // 2,
                      lidar_r * 2, 6))
    # Slit window in the dome (cyan strip).
    pygame.draw.rect(surface, C.UR_ACCENT,
                     (lidar_cx - lidar_r + 2, lidar_cy + lidar_r - 4,
                      lidar_r * 2 - 4, 2))

    # --- 3-segment status tower (mode indicator) ---
    tower_x = base_x - 30
    tower_top = chassis_top - 56
    tower_w = 16
    seg_h = 16
    _MODE_TOWER = {
        "IDLE":         (1, 0, 0),   # green only
        "BALL  CATCH":  (1, 1, 0),   # green + amber
        "TALK TO ARM":  (0, 1, 0),   # amber only
        "TYPING…":      (0, 1, 0),
        "LISTENING":    (0, 1, 0),
        "TRANSCRIBING": (0, 1, 0),
        "TASK  EXEC":   (1, 1, 0),
        "REHEARSAL":    (1, 1, 0),
        "RESET":        (0, 0, 1),
    }
    seg_active = _MODE_TOWER.get(mode_label, (1, 0, 0))
    seg_colors = (C.LED_GREEN, C.LED_AMBER, C.LED_RED)
    seg_off = C.UR_BODY_SHADOW
    pulse = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(2 * math.pi * now_ms / 1.4))
    # Backplate.
    pygame.draw.rect(surface, C.UR_JOINT_HOUSING,
                     (tower_x, tower_top, tower_w, seg_h * 3 + 6))
    for i in range(3):
        sy = tower_top + 3 + i * seg_h
        on = seg_active[i] == 1
        col = seg_colors[i] if on else seg_off
        if on:
            col = tuple(int(c * pulse + C.UR_BODY_SHADOW[k] * (1 - pulse))
                        for k, c in enumerate(col))
        pygame.draw.rect(surface, col,
                         (tower_x + 2, sy, tower_w - 4, seg_h - 4))

    # --- Cable conduit from chassis up to the J1 joint ---
    if top_y < chassis_top:
        conduit_pts = R.cubic_bezier(
            (base_x - 6, chassis_top + 2),
            (base_x - 14, (chassis_top + top_y) / 2),
            (base_x - 6, (chassis_top + top_y) / 2 + 12),
            (base_x, top_y + 6),
            n=14,
        )
        if len(conduit_pts) >= 2:
            pygame.draw.lines(surface, C.UR_CABLE, False,
                              [(int(p[0]), int(p[1])) for p in conduit_pts], 3)
        # Conduit collar at base.
        pygame.draw.rect(surface, C.UR_JOINT_HOUSING,
                         (base_x - 9, chassis_top, 6, 6))

    # --- Headlight/status LEDs on top of the chassis (mode colour pulse) ---
    _MODE_LED_COLORS = {
        "IDLE": C.LED_GREEN,
        "BALL  CATCH": C.UR_ACCENT,
        "TALK TO ARM": C.UR_ACCENT,
        "TYPING…": C.UR_ACCENT,
        "LISTENING": C.LED_AMBER,
        "TRANSCRIBING": C.LED_AMBER,
        "TASK  EXEC": C.LED_GREEN,
        "REHEARSAL": C.UR_ACCENT,
        "RESET": C.INDUSTRIAL_INK_SOFT,
    }
    led_color = _MODE_LED_COLORS.get(mode_label, C.UR_ACCENT)
    pulse_period = 0.6 if thinking else 1.6
    pulse_depth = 0.55 if thinking else 0.30
    led_pulse = 1.0 - pulse_depth * (0.5 + 0.5 * math.sin(2 * math.pi * now_ms / pulse_period))
    led_pulsed = tuple(
        max(0, min(255, int(led_color[k] * led_pulse + C.UR_BODY[k] * (1 - led_pulse))))
        for k in range(3)
    )
    for side in (-1, +1):
        lx = base_x + side * 28
        ly = chassis_top + 6
        pygame.draw.circle(surface, led_pulsed, (lx, ly), 4)
        pygame.draw.circle(surface, C.UR_BOLT, (lx, ly), 4, 1)
        if thinking:
            halo_r = 5 + int(7 * (1 - led_pulse))
            with contextlib.suppress(pygame.error):
                pygame.draw.circle(surface, led_pulsed, (lx, ly), halo_r, 1)

    # AI "thinking" radar — sweep an arc around the lidar dome while a
    # parse is in flight. Visible signal that an LLM call is happening.
    if thinking:
        radar_cx, radar_cy = lidar_cx, lidar_cy + lidar_r // 2
        radar_r = lidar_r + 10
        sweep_speed = 2.4 * math.pi  # radians/sec
        head = (now_ms * sweep_speed) % (2 * math.pi)
        for k in range(24):
            theta = head - k * (math.pi / 18)
            dist = (head - theta) % (2 * math.pi)
            if dist > math.pi / 2:
                continue
            fade = 1.0 - dist / (math.pi / 2)
            x1 = radar_cx + radar_r * math.cos(theta - math.pi)
            y1 = radar_cy + radar_r * math.sin(theta - math.pi)
            x2 = radar_cx + (radar_r + 6) * math.cos(theta - math.pi)
            y2 = radar_cy + (radar_r + 6) * math.sin(theta - math.pi)
            blended = tuple(
                int(C.INDUSTRIAL_FLOOR[k2] + (C.UR_ACCENT[k2] - C.INDUSTRIAL_FLOOR[k2]) * fade)
                for k2 in range(3)
            )
            with contextlib.suppress(pygame.error):
                pygame.draw.line(surface, blended,
                                 (int(x1), int(y1)), (int(x2), int(y2)), 2)


def _draw_motor(
    surface: pygame.Surface,
    center: tuple[float, float],
    radius: int,
    angle: float = 0.0,
    label: str | None = None,
    active: bool = True,
    seed: int = 0,
) -> None:
    """UR-style joint actuator: dark outer flange with bolt dots + lighter
    inner rotor disc with a single cyan radial index mark that rotates
    with the joint angle (so the audience sees the joint actually turning)
    + a status LED on the housing rim."""
    cx, cy = int(center[0]), int(center[1])

    # Outer flange (dark housing).
    R.aa_circle(surface, fill=C.UR_JOINT_HOUSING, outline=C.UR_JOINT_HOUSING,
                center=(cx, cy), radius=radius)

    # Bolt pattern around the rim.
    bolt_r = max(2, radius // 9)
    bolt_orbit = radius - bolt_r * 2 - 2
    for k in range(8):
        theta = k * math.pi / 4
        bx = cx + bolt_orbit * math.cos(theta)
        by = cy + bolt_orbit * math.sin(theta)
        pygame.draw.circle(surface, C.UR_BOLT,
                           (int(bx), int(by)), bolt_r)

    # Inner rotor disc (lighter dark grey).
    rotor_r = max(4, int(radius * 0.55))
    R.aa_circle(surface, fill=C.UR_JOINT_FACE, outline=C.UR_BOLT,
                center=(cx, cy), radius=rotor_r, width=1)

    # Cyan radial index mark — rotates with `angle`.
    mark_x = cx + (rotor_r - 3) * math.cos(angle)
    mark_y = cy + (rotor_r - 3) * math.sin(angle)
    pygame.draw.line(surface, C.UR_ACCENT,
                     (cx, cy), (int(mark_x), int(mark_y)), 3)
    # Center hub dot, with a soft powered bloom behind it.
    R.aa_glow_dot(surface, cx, cy, 2)
    pygame.draw.circle(surface, C.UR_ACCENT, (cx, cy), 2)

    # Status LED on the rim (top-right).
    led = (int(cx + radius * 0.65), int(cy - radius * 0.65))
    led_color = C.LED_GREEN if active else C.LED_AMBER
    pygame.draw.circle(surface, led_color, led, max(2, bolt_r))
    pygame.draw.circle(surface, C.UR_BOLT, led, max(2, bolt_r), 1)


def _draw_gripper(
    surface: pygame.Surface,
    ee_xz: tuple[float, float],
    angle_world: float,
    open_fraction: float,
) -> None:
    """UR-style parallel-jaw gripper: wrist mount plate, two horizontal
    rails, two carriages sliding apart/together with `open_fraction`,
    each carriage carrying a knurled-pad jaw. A small wrist camera sits
    on the back of the mount.

    `ee_xz` is the end-effector position in WORLD coordinates (the caller
    is expected to add anchor_world_x to the arm-local end_effector).
    """
    ex_px, ey_px = world_to_screen(*ee_xz)
    angle_screen = -angle_world
    fwd = (math.cos(angle_screen), math.sin(angle_screen))
    perp = (-fwd[1], fwd[0])

    def _world_at(dl: float, dw: float) -> tuple[float, float]:
        return (ex_px + fwd[0] * dl + perp[0] * dw,
                ey_px + fwd[1] * dl + perp[1] * dw)

    # 1. Wrist mount plate (white, rounded-rect feel) straddling the EE.
    plate_len, plate_w = 14, 32
    plate_corners = [_world_at(-plate_len, -plate_w),
                     _world_at(-plate_len, +plate_w),
                     _world_at(+plate_len, +plate_w),
                     _world_at(+plate_len, -plate_w)]
    R.aa_polygon(surface, fill=C.UR_BODY, outline=C.UR_BODY_OUTLINE,
                 points=plate_corners, width=2)
    # Four bolt dots on the plate corners.
    for dl in (-plate_len + 4, +plate_len - 4):
        for dw in (-plate_w + 4, +plate_w - 4):
            bx, by = _world_at(dl, dw)
            pygame.draw.circle(surface, C.UR_BOLT, (int(bx), int(by)), 2)

    # 2. Wrist camera — small dark cube on the back of the mount with a
    #    single cyan lens dot. Tells the viewer "this end can see".
    cam_corners = [_world_at(-plate_len - 8, -7),
                   _world_at(-plate_len - 8, +7),
                   _world_at(-plate_len, +7),
                   _world_at(-plate_len, -7)]
    R.aa_polygon(surface, fill=C.UR_JOINT_HOUSING, outline=C.UR_BOLT,
                 points=cam_corners, width=1)
    cam_center_x, cam_center_y = _world_at(-plate_len - 4, 0)
    pygame.draw.circle(surface, C.UR_ACCENT,
                       (int(cam_center_x), int(cam_center_y)), 2)

    # 3. Two horizontal rails (dark grey) along the perpendicular axis,
    #    extending past the plate edges so the jaws can slide.
    block_half_px = BLOCK_HALF * C.PX_PER_M
    rail_extent = block_half_px + 30
    for dl in (+plate_len + 6, +plate_len + 18):
        ra = _world_at(dl, -rail_extent)
        rb = _world_at(dl, +rail_extent)
        pygame.draw.line(surface, C.UR_BOLT,
                         (int(ra[0]), int(ra[1])),
                         (int(rb[0]), int(rb[1])), 2)

    # 4. Two carriages + jaws — each carriage is a small white square on
    #    the rails, the jaw extends forward past the rails.
    gap_closed = block_half_px + 4
    gap_open = block_half_px + 28
    gap = gap_closed + open_fraction * (gap_open - gap_closed)

    carriage_l, carriage_w = 14, 18
    jaw_len = 36
    jaw_w = 14

    for side in (+1, -1):
        # Carriage center sits between the rails (at dl ~+plate_len+12).
        carriage_dl = plate_len + 12
        carriage_dw = side * gap

        # Carriage body.
        c_corners = [
            _world_at(carriage_dl - carriage_l / 2,
                      carriage_dw - carriage_w / 2),
            _world_at(carriage_dl - carriage_l / 2,
                      carriage_dw + carriage_w / 2),
            _world_at(carriage_dl + carriage_l / 2,
                      carriage_dw + carriage_w / 2),
            _world_at(carriage_dl + carriage_l / 2,
                      carriage_dw - carriage_w / 2),
        ]
        R.aa_polygon(surface, fill=C.UR_BODY, outline=C.UR_BODY_OUTLINE,
                     points=c_corners, width=1)

        # Jaw (extends forward past the carriage).
        jaw_dl_start = carriage_dl + carriage_l / 2
        jaw_dl_end = jaw_dl_start + jaw_len
        # Jaw inner edge sits at carriage_dw - side*jaw_w/2 (toward the gap).
        jaw_inner = carriage_dw - side * jaw_w / 2
        jaw_outer = carriage_dw + side * jaw_w / 2
        j_corners = [
            _world_at(jaw_dl_start, jaw_inner),
            _world_at(jaw_dl_start, jaw_outer),
            _world_at(jaw_dl_end, jaw_outer),
            _world_at(jaw_dl_end, jaw_inner),
        ]
        R.aa_polygon(surface, fill=C.UR_BODY, outline=C.UR_BODY_OUTLINE,
                     points=j_corners, width=2)

        # Knurled black contact pad on the inner face of the jaw.
        pad_inset_dl = 4
        pad_corners = [
            _world_at(jaw_dl_start + pad_inset_dl, jaw_inner),
            _world_at(jaw_dl_start + pad_inset_dl,
                      jaw_inner - side * 4),
            _world_at(jaw_dl_end - pad_inset_dl,
                      jaw_inner - side * 4),
            _world_at(jaw_dl_end - pad_inset_dl, jaw_inner),
        ]
        R.aa_polygon(surface, fill=C.UR_JOINT_HOUSING, outline=None,
                     points=pad_corners)

        # Cyan force-sensor dot at the jaw tip (inner face).
        sensor_x, sensor_y = _world_at(jaw_dl_end - 6, jaw_inner - side * 2)
        pygame.draw.circle(surface, C.UR_ACCENT,
                           (int(sensor_x), int(sensor_y)), 2)


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
    arm_state=None,
    anchor_world_x: float | None = None,
    link_lengths: tuple[float, ...] | None = None,
    gripper_state: dict | None = None,
) -> None:
    """Robot arm: structural links, servo motors, and a two-finger gripper.

    Rendered from the controller's commanded pose (forward-kinematics of the
    joint target), not the noisy physics body_q — this keeps the arm visually
    steady even when the XPBD solver oscillates a few millimetres around the
    set-point. Screen Y flips relative to world Z, so rotation angles negate.

    `holding=True` closes the gripper around a carried block. The state is
    smoothed per-frame so the transition is visible to the audience.

    By default this draws the primary (Newton-backed) arm anchored at
    `world.base_x`. Pass `arm_state` + `anchor_world_x` + `link_lengths` to
    render a secondary FK-only rig (Arm B) anchored elsewhere; gripper_state
    can be passed in to keep the gripper open/close low-pass independent
    per arm.
    """
    if arm_state is None:
        st = world.arm_state_from_target()
        base_offset = world.base_x
        link_lengths_local = world.link_lengths
    else:
        st = arm_state
        base_offset = (anchor_world_x if anchor_world_x is not None
                       else world.base_x)
        link_lengths_local = (link_lengths if link_lengths is not None
                              else world.link_lengths)

    # ---------------- UR-style link assembly --------------------------
    # Each link is rendered as a 3-piece assembly: dark proximal joint
    # shell → white cylindrical body (with a cylindrical shadow band along
    # the lower edge for fake 3D) → dark distal joint shell. A subtle
    # wraparound seam at each end sells the "two parts bolted together"
    # feel; a thin cable bundle Bézier curves between joints.

    def _rot(local: tuple[float, float], cx: float, cy: float,
             cos_a: float, sin_a: float) -> tuple[float, float]:
        return (cx + cos_a * local[0] - sin_a * local[1],
                cy + sin_a * local[0] + cos_a * local[1])

    body_half_h = LINK_HALF_W * C.PX_PER_M * 2.1   # white tube radius (px)
    shadow_band_h = body_half_h * 0.45             # shadow band thickness
    joint_r = int(body_half_h + 6)                 # joint shell radius
    seam_inset = 4                                 # px between joint and body

    ends_px = [local_to_screen(x, z, base_offset) for x, z in st.link_world_ends]

    for _i, (pose, length) in enumerate(zip(st.link_poses, link_lengths_local, strict=True)):
        cx_px, cy_px = local_to_screen(*pose.center_xz, base_offset)
        screen_angle = -pose.angle
        cos_a, sin_a = math.cos(screen_angle), math.sin(screen_angle)
        half_w_px = (length * C.PX_PER_M) / 2
        # Slightly inset the body so the joint shells fully cover the
        # body's rounded ends — no seam visible at any angle.
        body_half_w = half_w_px - seam_inset

        # 1. White cylindrical body. Drawn as a rotated rectangle polygon.
        body_corners_local = [
            (-body_half_w, -body_half_h),
            (+body_half_w, -body_half_h),
            (+body_half_w, +body_half_h),
            (-body_half_w, +body_half_h),
        ]
        body_corners = [_rot(p, cx_px, cy_px, cos_a, sin_a)
                        for p in body_corners_local]
        R.aa_polygon(surface, fill=C.UR_BODY,
                     outline=C.UR_BODY_OUTLINE,
                     points=body_corners, width=2)

        # 2. Cylindrical shadow band along the lower edge of the tube
        #    (in link-local frame; rotated with screen_angle).
        shadow_corners_local = [
            (-body_half_w + 2, +body_half_h - shadow_band_h),
            (+body_half_w - 2, +body_half_h - shadow_band_h),
            (+body_half_w - 2, +body_half_h - 2),
            (-body_half_w + 2, +body_half_h - 2),
        ]
        shadow_corners = [_rot(p, cx_px, cy_px, cos_a, sin_a)
                          for p in shadow_corners_local]
        R.aa_polygon(surface, fill=C.UR_BODY_SHADOW,
                     outline=None, points=shadow_corners)

        # 3. Cyan status strip near the upper edge — small filled rect that
        #    glows when the joint is loaded. For now, always-on UR_ACCENT.
        strip_corners_local = [
            (-body_half_w * 0.55, -body_half_h + 4),
            (+body_half_w * 0.55, -body_half_h + 4),
            (+body_half_w * 0.55, -body_half_h + 9),
            (-body_half_w * 0.55, -body_half_h + 9),
        ]
        strip_corners = [_rot(p, cx_px, cy_px, cos_a, sin_a)
                         for p in strip_corners_local]
        R.aa_polygon(surface, fill=C.UR_ACCENT,
                     outline=None, points=strip_corners)

        # 4. Wraparound seam at each end of the body — thin dark line
        #    inside the body, suggesting the body bolts to the joint shell.
        for end_x in (-body_half_w + 6, +body_half_w - 6):
            seam_a = _rot((end_x, -body_half_h + 1),
                          cx_px, cy_px, cos_a, sin_a)
            seam_b = _rot((end_x, +body_half_h - 1),
                          cx_px, cy_px, cos_a, sin_a)
            pygame.draw.line(surface, C.UR_BODY_OUTLINE,
                             (int(seam_a[0]), int(seam_a[1])),
                             (int(seam_b[0]), int(seam_b[1])), 1)

        # 5. Cable bundle — soft dark curve looping outside the body
        #    between the two joint centres. Bezier control points sit a
        #    half-thickness below the body so the cable hangs visually.
        cable_a = _rot((-half_w_px, body_half_h * 1.5),
                       cx_px, cy_px, cos_a, sin_a)
        cable_d = _rot((+half_w_px, body_half_h * 1.5),
                       cx_px, cy_px, cos_a, sin_a)
        cable_b = _rot((-half_w_px * 0.45, body_half_h * 2.1),
                       cx_px, cy_px, cos_a, sin_a)
        cable_c = _rot((+half_w_px * 0.45, body_half_h * 2.1),
                       cx_px, cy_px, cos_a, sin_a)
        cable_pts = R.cubic_bezier(cable_a, cable_b, cable_c, cable_d, n=18)
        if len(cable_pts) >= 2:
            pygame.draw.lines(surface, C.UR_CABLE, False,
                              [(int(p[0]), int(p[1])) for p in cable_pts], 2)

    # ---------------- joint shells (drawn AFTER bodies so shells overlap
    # body ends, hiding any sub-pixel seam) -----------------------------
    cumulative_angle = 0.0
    for i, pt in enumerate(ends_px[:-1]):   # skip the EE end
        # Cumulative angle of joint i = sum of joint angles up to i,
        # but inverted because screen Y is flipped.
        if i < len(st.link_poses):
            cumulative_angle = -st.link_poses[i].angle
        _draw_motor(
            surface, pt,
            radius=joint_r,
            angle=cumulative_angle,
            seed=200 + i,
        )

    # Gripper at the end effector. Because the arm is FK-rendered from the
    # controller target (already smooth), no extra low-pass is needed on
    # the hand angle — use it directly for responsive catch poses.
    hand_angle = st.link_poses[-1].angle if st.link_poses else 0.0

    target_open = 0.0 if holding else 1.0
    g_state = gripper_state if gripper_state is not None else _GRIPPER_STATE
    open_fraction = _update_gripper_state(target_open, frame_dt, g_state)
    ee_world = (st.end_effector[0] + base_offset, st.end_effector[1])
    # Floor shadow under the gripper; shrinks and fades as the arm lifts, so the
    # audience reads reach height during the hero pick-and-place.
    g_sx, _ = world_to_screen(ee_world[0], 0.0)
    g_sc = max(0.25, min(1.0, 1.0 - st.end_effector[1] / 1.2))
    if 0 <= g_sx <= C.VIEWPORT_WIDTH:
        R.ground_shadow(surface, g_sx, C.GROUND_Y_PX,
                        rx=int(34 * g_sc), ry=max(3, int(9 * g_sc)), strength=g_sc)
    _draw_gripper(surface, ee_world, hand_angle, open_fraction)

