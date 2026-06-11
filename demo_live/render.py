"""Hand-drawn rendering primitives for the academic whiteboard style.

Every primitive has a tiny deterministic jitter so straight lines feel chalked,
circles feel sketched, and the whole scene reads as "drawn live on a board."
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence

import pygame

from . import config as C

# A single global RNG keyed per-surface-call — jitter should look stable frame
# to frame (otherwise lines buzz and it looks broken).
_JITTER_RNG = random.Random(42)

# Precomputed deterministic jitter in [-1, 1]. Sketch primitives index this by
# (base_seed + segment_index) instead of constructing a random.Random per call
# and calling uniform() per segment — the profiler flagged that as a render
# hot spot. Same primitive → same jitter every frame (stable, no buzz);
# different primitives index different table slices, so they still look varied.
# Size is a power of two so the index wraps with a cheap bit-mask.
_JITTER_N = 4096
_JITTER_MASK = _JITTER_N - 1
_JITTER = [_JITTER_RNG.uniform(-1.0, 1.0) for _ in range(_JITTER_N)]


def _segmented(p0: tuple[float, float], p1: tuple[float, float], n: int) -> list[tuple[float, float]]:
    return [
        (
            p0[0] + (p1[0] - p0[0]) * t,
            p0[1] + (p1[1] - p0[1]) * t,
        )
        for t in [i / n for i in range(n + 1)]
    ]


def _perp_unit(p0: tuple[float, float], p1: tuple[float, float]) -> tuple[float, float]:
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    mag = math.hypot(dx, dy) or 1.0
    return -dy / mag, dx / mag


def sketch_line(
    surface: pygame.Surface,
    color: tuple[int, int, int],
    start: tuple[float, float],
    end: tuple[float, float],
    width: int = C.LINE_WIDTH_MEDIUM,
    wobble: float = C.WOBBLE,
    seed: int = 0,
) -> None:
    """Draw a straight-ish line with per-segment perpendicular jitter."""
    base = seed or hash((start, end))
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    n = max(4, int(length / 20))
    pts = _segmented(start, end, n)
    px, py = _perp_unit(start, end)
    wobbled = [pts[0]]
    for i, pt in enumerate(pts[1:-1]):
        j = _JITTER[(base + i) & _JITTER_MASK] * wobble
        wobbled.append((pt[0] + px * j, pt[1] + py * j))
    wobbled.append(pts[-1])
    if len(wobbled) >= 2:
        pygame.draw.lines(surface, color, False, wobbled, width)


def sketch_polyline(
    surface: pygame.Surface,
    color: tuple[int, int, int],
    points: Sequence[tuple[float, float]],
    width: int = C.LINE_WIDTH_MEDIUM,
    wobble: float = C.WOBBLE,
    seed: int = 0,
) -> None:
    """A chain of `sketch_line` calls sharing a deterministic seed."""
    for i, (a, b) in enumerate(zip(points[:-1], points[1:], strict=True)):
        sketch_line(surface, color, a, b, width=width, wobble=wobble, seed=seed + i * 17)


def sketch_rect(
    surface: pygame.Surface,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    center: tuple[float, float],
    half_w: float,
    half_h: float,
    angle: float = 0.0,
    width: int = C.LINE_WIDTH_MEDIUM,
    seed: int = 0,
) -> None:
    """Filled sketch rectangle, rotated around center by `angle` radians."""
    cx, cy = center
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    corners_local = [
        (-half_w, -half_h),
        (half_w, -half_h),
        (half_w, half_h),
        (-half_w, half_h),
    ]
    corners = [(cx + cos_a * x - sin_a * y, cy + sin_a * x + cos_a * y) for x, y in corners_local]
    pygame.draw.polygon(surface, fill, corners)
    sketch_polyline(surface, outline, corners + [corners[0]], width=width, seed=seed)


def sketch_circle(
    surface: pygame.Surface,
    fill: tuple[int, int, int] | None,
    outline: tuple[int, int, int],
    center: tuple[float, float],
    radius: float,
    width: int = C.LINE_WIDTH_MEDIUM,
    seed: int = 0,
) -> None:
    base = seed or int(center[0])
    n = 28
    pts = []
    for i in range(n + 1):
        t = (i / n) * 2 * math.pi
        jitter = _JITTER[(base + i) & _JITTER_MASK] * C.WOBBLE
        r = radius + jitter
        pts.append((center[0] + r * math.cos(t), center[1] + r * math.sin(t)))
    if fill is not None:
        pygame.draw.polygon(surface, fill, pts)
    pygame.draw.lines(surface, outline, True, pts, width)


def sketch_dashed_line(
    surface: pygame.Surface,
    color: tuple[int, int, int],
    start: tuple[float, float],
    end: tuple[float, float],
    width: int = 2,
    dash: int = 14,
    gap: int = 10,
) -> None:
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if length == 0:
        return
    ux, uy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
    step = dash + gap
    t = 0.0
    while t < length:
        a = (start[0] + ux * t, start[1] + uy * t)
        t2 = min(t + dash, length)
        b = (start[0] + ux * t2, start[1] + uy * t2)
        pygame.draw.line(surface, color, a, b, width)
        t += step


def paper_background(surface: pygame.Surface) -> None:
    """Off-white background with a faint grid, like engineering notebook paper."""
    surface.fill(C.PAPER)
    # Grid every 40 px
    w, h = surface.get_size()
    for x in range(0, w, 40):
        pygame.draw.line(surface, C.GRID, (x, 0), (x, h), 1)
    for y in range(0, h, 40):
        pygame.draw.line(surface, C.GRID, (0, y), (w, y), 1)


# ------------------------------------------------------------------ industrial primitives
# Used by the UR-style scene rewrite. Anti-aliased + crisp, no jitter.

def aa_polygon(
    surface: pygame.Surface,
    fill: tuple[int, int, int] | None,
    outline: tuple[int, int, int] | None,
    points: Sequence[tuple[float, float]],
    width: int = 1,
) -> None:
    """Anti-aliased filled polygon with optional outline. Pygame's
    pygame.gfxdraw.aapolygon + filled_polygon gives the cleanest result;
    fall back to plain pygame.draw.polygon if gfxdraw unavailable."""
    int_pts = [(int(round(x)), int(round(y))) for x, y in points]
    try:
        from pygame import gfxdraw
        if fill is not None:
            gfxdraw.filled_polygon(surface, int_pts, fill)
        if outline is not None:
            gfxdraw.aapolygon(surface, int_pts, outline)
            if width > 1:
                pygame.draw.polygon(surface, outline, int_pts, width)
    except ImportError:
        if fill is not None:
            pygame.draw.polygon(surface, fill, int_pts)
        if outline is not None:
            pygame.draw.polygon(surface, outline, int_pts, width)


def aa_circle(
    surface: pygame.Surface,
    fill: tuple[int, int, int] | None,
    outline: tuple[int, int, int] | None,
    center: tuple[float, float],
    radius: float,
    width: int = 1,
) -> None:
    """Anti-aliased filled circle with optional crisp outline."""
    cx, cy = int(round(center[0])), int(round(center[1]))
    r = int(round(radius))
    if r < 1:
        return
    try:
        from pygame import gfxdraw
        if fill is not None:
            gfxdraw.filled_circle(surface, cx, cy, r, fill)
        if outline is not None:
            gfxdraw.aacircle(surface, cx, cy, r, outline)
            if width > 1:
                pygame.draw.circle(surface, outline, (cx, cy), r, width)
    except ImportError:
        if fill is not None:
            pygame.draw.circle(surface, fill, (cx, cy), r)
        if outline is not None:
            pygame.draw.circle(surface, outline, (cx, cy), r, width)


def aa_rounded_rect(
    surface: pygame.Surface,
    fill: tuple[int, int, int] | None,
    outline: tuple[int, int, int] | None,
    rect: tuple[int, int, int, int],
    radius: int = 8,
    width: int = 1,
) -> None:
    """Rounded rectangle. Pygame's draw.rect supports `border_radius`
    natively from 2.0+; we use that for the fill and add a thin outline."""
    x, y, w, h = rect
    radius = max(0, min(radius, w // 2, h // 2))
    if fill is not None:
        pygame.draw.rect(surface, fill, (x, y, w, h), border_radius=radius)
    if outline is not None:
        pygame.draw.rect(surface, outline, (x, y, w, h),
                         width=width, border_radius=radius)


def vertical_gradient_strip(
    surface: pygame.Surface,
    rect: tuple[int, int, int, int],
    top_color: tuple[int, int, int],
    bot_color: tuple[int, int, int],
) -> None:
    """Cheap pixel-row vertical gradient inside `rect`. Used for the
    cylindrical-tube illusion on the UR arm body."""
    x, y, w, h = rect
    for i in range(h):
        t = i / max(1, h - 1)
        c = tuple(int(top_color[k] + (bot_color[k] - top_color[k]) * t)
                  for k in range(3))
        pygame.draw.line(surface, c, (x, y + i), (x + w - 1, y + i))


_SHADOW_CACHE: dict[tuple[int, int, float], pygame.Surface] = {}


def ground_shadow(
    surface: pygame.Surface,
    cx: float,
    floor_y: float,
    rx: float,
    ry: float,
    strength: float = 1.0,
) -> None:
    """Soft translucent contact shadow — a stacked dark ellipse on the floor at
    (cx, floor_y) that grounds the object drawn above it. Surfaces are cached by
    (rx, ry, strength) so there is zero per-frame allocation, and the cached
    surface is never mutated (immutable: vary by key, not in place)."""
    rx, ry = int(rx), int(ry)
    if rx < 2 or ry < 2:
        return
    key = (rx, ry, round(float(strength), 2))
    shadow = _SHADOW_CACHE.get(key)
    if shadow is None:
        w, h = 2 * rx + 4, 2 * ry + 4
        shadow = pygame.Surface((w, h), pygame.SRCALPHA)
        layers = 4
        for i in range(layers):
            frac = 1.0 - 0.72 * i / (layers - 1)          # 1.0 (outer, faint) → 0.28 (inner, dark)
            alpha = int(max(0, min(120, (16 + 24 * i) * strength)))
            ew, eh = max(1, int(w * frac)), max(1, int(h * frac))
            pygame.draw.ellipse(shadow, (*C.INDUSTRIAL_INK, alpha),
                                ((w - ew) // 2, (h - eh) // 2, ew, eh))
        _SHADOW_CACHE[key] = shadow
    surface.blit(shadow, (int(cx - shadow.get_width() / 2),
                          int(floor_y - shadow.get_height() / 2)))


_GLOW_CACHE: dict[tuple[int, tuple[int, int, int]], pygame.Surface] = {}


def aa_glow_dot(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    r: float,
    color: tuple[int, int, int] = C.UR_ACCENT,
) -> None:
    """Soft additive bloom behind an accent dot so it reads as a powered, lit
    indicator rather than a flat printed dot. Cached per (radius, color) and
    blitted additively; the cached surface is never mutated."""
    r = int(r)
    if r < 1:
        return
    key = (r, tuple(color))
    glow = _GLOW_CACHE.get(key)
    if glow is None:
        gr = max(3, r * 4)
        glow = pygame.Surface((2 * gr, 2 * gr), pygame.SRCALPHA)
        for rr, a in ((gr, 16), (int(gr * 0.66), 34), (int(gr * 0.4), 60)):
            pygame.draw.circle(glow, (*color, a), (gr, gr), max(1, rr))
        _GLOW_CACHE[key] = glow
    surface.blit(glow, (int(cx - glow.get_width() / 2), int(cy - glow.get_height() / 2)),
                 special_flags=pygame.BLEND_RGBA_ADD)


def cubic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    n: int = 24,
) -> list[tuple[float, float]]:
    """Sample a cubic Bezier curve at n+1 points. Used for cable routing."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = (u * u * u * p0[0] + 3 * u * u * t * p1[0]
             + 3 * u * t * t * p2[0] + t * t * t * p3[0])
        y = (u * u * u * p0[1] + 3 * u * u * t * p1[1]
             + 3 * u * t * t * p2[1] + t * t * t * p3[1])
        pts.append((x, y))
    return pts


# ------------------------------------------------------------------ fonts
_FONT_CACHE: dict[tuple[str, int], pygame.font.Font] = {}


def font(path: str, size: int) -> pygame.font.Font:
    key = (path, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = pygame.font.Font(path, size)
    return _FONT_CACHE[key]


def text(
    surface: pygame.Surface,
    s: str,
    pos: tuple[int, int],
    size: int = C.SIZE_BODY,
    color: tuple[int, int, int] = C.INK,
    font_path: str = C.FONT_BODY,
    anchor: str = "tl",
) -> pygame.Rect:
    """Draw text. `anchor` = 'tl' | 'center' | 'tr' | 'bl'."""
    surf = font(font_path, size).render(s, True, color)
    rect = surf.get_rect()
    if anchor == "tl":
        rect.topleft = pos
    elif anchor == "center":
        rect.center = pos
    elif anchor == "tr":
        rect.topright = pos
    elif anchor == "bl":
        rect.bottomleft = pos
    surface.blit(surf, rect)
    return rect
