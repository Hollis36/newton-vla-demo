"""Scene workspace primitives that are NOT the arm itself: ground / floor,
ball + its trajectory + launch preview + intercept marker, and the
block stack. The arm + gripper render lives in `scene.arm`.
"""

from __future__ import annotations

import contextlib
import math

import pygame

from .. import config as C
from .. import render as R
from ..physics import BLOCK_HALF, World, world_to_screen


def draw_ground(surface: pygame.Surface) -> None:
    """UR-style industrial floor — light grey base + faint grid + a single
    crisp baseline at ground level + a subtle anti-static safety stripe."""
    # Floor fill (above and below the ground line).
    pygame.draw.rect(surface, C.INDUSTRIAL_FLOOR,
                     (0, 0, C.VIEWPORT_WIDTH, C.HEIGHT))
    # Faint 40-px grid covers the working area (ABOVE the ground line).
    for x in range(0, C.VIEWPORT_WIDTH, 40):
        pygame.draw.line(surface, C.INDUSTRIAL_FLOOR_LINE,
                         (x, 0), (x, C.GROUND_Y_PX), 1)
    for y in range(0, C.GROUND_Y_PX, 40):
        pygame.draw.line(surface, C.INDUSTRIAL_FLOOR_LINE,
                         (0, y), (C.VIEWPORT_WIDTH, y), 1)
    # Anti-static safety stripe — two thin horizontal lines just above the
    # ground line, with diagonal hatch fill between them. Reads as a
    # marked safety zone in factory floor.
    stripe_top = C.GROUND_Y_PX - 6
    stripe_bot = C.GROUND_Y_PX - 2
    pygame.draw.rect(surface, C.UR_ACCENT_SOFT,
                     (0, stripe_top, C.VIEWPORT_WIDTH, stripe_bot - stripe_top))
    # Crisp ground baseline.
    pygame.draw.line(surface, C.INDUSTRIAL_INK,
                     (0, C.GROUND_Y_PX),
                     (C.VIEWPORT_WIDTH, C.GROUND_Y_PX),
                     2)
    # Below the ground line: darker tone (think under-floor / off-stage).
    pygame.draw.rect(surface, C.UR_BODY_SHADOW,
                     (0, C.GROUND_Y_PX + 1,
                      C.VIEWPORT_WIDTH, C.HEIGHT - C.GROUND_Y_PX))
    # Floor tile seam lines below the baseline (every 60 px, perspective-y).
    for x in range(0, C.VIEWPORT_WIDTH, 60):
        pygame.draw.line(surface, C.INDUSTRIAL_FLOOR_LINE,
                         (x, C.GROUND_Y_PX + 4),
                         (x, C.HEIGHT), 1)



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


def draw_blocks(
    surface: pygame.Surface,
    world: World,
    target_color: str | None = None,
) -> None:
    """Machined-plastic parts. Crisp polygon edges, soft 3D highlight on
    the upper-left corner, lasered serial label on the front face. The
    target halo (active block currently being acted on by the executor)
    pulses in cool UR cyan around the part.
    """
    now_ms = pygame.time.get_ticks() / 1000.0
    serial_idx = {"red": "01", "green": "02", "blue": "03", "yellow": "04"}
    for block, (x, z), rot in world.block_poses():
        cx, cy = world_to_screen(x, z)
        half_px = int(BLOCK_HALF * C.PX_PER_M)
        # Use the softer "machined" palette tokens; legacy BLOCK_COLORS
        # stays for any non-renderer code paths.
        color = C.UR_BLOCK_COLORS.get(block.color, C.UR_BODY_OUTLINE)

        # Target halo: pulsing cyan ring (NOT the block colour) for clear
        # "this is the focus" cue against the white machinery.
        if target_color is not None and block.color == target_color:
            pulse = 0.5 + 0.5 * math.sin(2 * math.pi * now_ms / 1.2)
            radius_px = int(half_px * (1.55 + 0.18 * pulse))
            ring_w = max(2, int(3 * pulse + 2))
            with contextlib.suppress(pygame.error):
                pygame.draw.circle(surface, C.UR_ACCENT_SOFT,
                                   (cx, cy), radius_px, ring_w)
                pygame.draw.circle(surface, C.UR_ACCENT,
                                   (cx, cy), radius_px + 2, 1)

        # Rotated block geometry (square, axis-aligned for rot=0).
        cos_a, sin_a = math.cos(-rot), math.sin(-rot)
        corners_local = [(-half_px, -half_px), (+half_px, -half_px),
                         (+half_px, +half_px), (-half_px, +half_px)]
        corners = [(cx + cos_a * lx - sin_a * ly,
                    cy + sin_a * lx + cos_a * ly) for lx, ly in corners_local]
        # Body fill + crisp outline.
        R.aa_polygon(surface, fill=color, outline=C.INDUSTRIAL_INK,
                     points=corners, width=2)

        # Diagonal highlight stripe in the upper-left for fake 3D / "chamfer".
        hi_offset = int(half_px * 0.35)
        hi_corners_local = [
            (-half_px + 2, -half_px + 2),
            (-half_px + hi_offset, -half_px + 2),
            (-half_px + 2, -half_px + hi_offset),
        ]
        hi_corners = [(cx + cos_a * lx - sin_a * ly,
                       cy + sin_a * lx + cos_a * ly)
                      for lx, ly in hi_corners_local]
        # Lighter version of the body colour.
        hi = tuple(min(255, c + 40) for c in color)
        R.aa_polygon(surface, fill=hi, outline=None, points=hi_corners)

        # Lasered serial label on the front face.
        label = f"{block.color[:3].upper()}-{serial_idx.get(block.color, '00')}"
        R.text(surface, label,
               (cx, cy + half_px - 6),
               size=C.SIZE_SMALL,
               color=C.INDUSTRIAL_INK_SOFT,
               font_path=C.FONT_HEADING,
               anchor="center")
