"""Particle bursts and mode-change banners — visual rewards for the audience.

Each effect is self-contained: instantiate, feed dt per frame, draw each frame.
Once expired it removes itself.
"""

from __future__ import annotations

import contextlib
import math
import random
import time
from dataclasses import dataclass

import pygame

from . import config as C

# ---------------------------------------------------------------- particles

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float            # seconds remaining
    initial_life: float
    color: tuple[int, int, int]
    radius: float


@dataclass
class Banner:
    text: str
    color: tuple[int, int, int]
    born_at: float
    duration: float = 0.9
    y_band: int = 0        # 0 = under header, 1 = above footer


@dataclass
class Ring:
    x: float
    y: float
    color: tuple[int, int, int]
    born_at: float
    duration: float = 0.45
    max_radius: float = 80


@dataclass
class TrailSample:
    x: float
    y: float
    born_at: float


class EffectsLayer:
    TRAIL_MAX_AGE = 0.55       # seconds — full fade-out window
    TRAIL_MIN_DELTA = 4.0      # px — drop a new sample when EE has moved this far
    TRAIL_MAX_SAMPLES = 80

    def __init__(self) -> None:
        self.particles: list[Particle] = []
        self.banners: list[Banner] = []
        self.rings: list[Ring] = []
        # Motion trail behind the gripper. List of (x, y, born_at) tuples in
        # screen space, oldest first.
        self.trail: list[TrailSample] = []

    # ---------------------------------------------------- emitters

    def burst(
        self,
        xy: tuple[int, int],
        color: tuple[int, int, int] = C.ACCENT,
        count: int = 28,
        speed: float = 260.0,
        gravity: float = 500.0,
    ) -> None:
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            s = random.uniform(speed * 0.5, speed)
            self.particles.append(
                Particle(
                    x=xy[0], y=xy[1],
                    vx=math.cos(angle) * s,
                    vy=math.sin(angle) * s - 70,
                    life=random.uniform(0.45, 0.85),
                    initial_life=0.7,
                    color=color,
                    radius=random.uniform(3.0, 7.0),
                )
            )
        self.rings.append(Ring(xy[0], xy[1], color, time.perf_counter()))
        self._gravity = gravity

    def banner(
        self,
        text: str,
        color: tuple[int, int, int] = C.PRIMARY,
        duration: float = 0.9,
        y_band: int = 0,
    ) -> None:
        self.banners.append(Banner(text, color, time.perf_counter(), duration, y_band))

    def ring(
        self,
        xy: tuple[int, int],
        color: tuple[int, int, int] = C.ACCENT,
        duration: float = 0.45,
        max_radius: float = 80.0,
    ) -> None:
        """Emit a standalone expanding ring (no particles). Used to highlight
        a *decision* moment (e.g. catcher commit) where the audience benefits
        from seeing "the arm just made up its mind" without the visual noise
        of a celebratory burst."""
        self.rings.append(Ring(
            x=xy[0], y=xy[1],
            color=color,
            born_at=time.perf_counter(),
            duration=duration,
            max_radius=max_radius,
        ))

    def push_trail(self, xy: tuple[float, float]) -> None:
        """Append the current end-effector position. Drops near-duplicate
        consecutive samples so a stationary arm doesn't bloat the trail."""
        x, y = xy
        now = time.perf_counter()
        if self.trail:
            last = self.trail[-1]
            if math.hypot(x - last.x, y - last.y) < self.TRAIL_MIN_DELTA:
                return
        self.trail.append(TrailSample(x, y, now))
        if len(self.trail) > self.TRAIL_MAX_SAMPLES:
            self.trail = self.trail[-self.TRAIL_MAX_SAMPLES:]

    # ---------------------------------------------------- per-frame update

    def update(self, dt: float) -> None:
        g = getattr(self, "_gravity", 500.0)
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += g * dt
            # Mild air drag so particles don't fly off the screen.
            p.vx *= math.exp(-1.5 * dt)
            p.vy *= math.exp(-1.5 * dt)
            p.life -= dt
        self.particles = [p for p in self.particles if p.life > 0]

        now = time.perf_counter()
        self.banners = [b for b in self.banners if now - b.born_at < b.duration]
        self.rings = [r for r in self.rings if now - r.born_at < r.duration]
        self.trail = [t for t in self.trail if now - t.born_at < self.TRAIL_MAX_AGE]

    # ---------------------------------------------------- draw

    def draw(self, surface: pygame.Surface, font_heading_path: str) -> None:
        now = time.perf_counter()

        # Expanding rings (on catch / stack completion).
        for r in self.rings:
            t = (now - r.born_at) / r.duration
            t = max(0.0, min(1.0, t))
            radius = int(r.max_radius * t)
            if radius < 1:
                continue
            width = max(1, int(4 * (1 - t)))
            with contextlib.suppress(pygame.error):
                pygame.draw.circle(surface, r.color, (int(r.x), int(r.y)), radius, width)

        # Particles — opacity fades with remaining life.
        for p in self.particles:
            fade = p.life / p.initial_life if p.initial_life > 0 else 1
            fade = max(0.0, min(1.0, fade))
            rad = max(1, int(p.radius * fade))
            pygame.draw.circle(surface, p.color, (int(p.x), int(p.y)), rad)

        # End-effector motion trail. Each consecutive pair forms a segment
        # whose width and brightness fade with the older sample's age.
        if len(self.trail) >= 2:
            trail_color = C.UR_ACCENT
            for i in range(1, len(self.trail)):
                a = self.trail[i - 1]
                b = self.trail[i]
                age = now - a.born_at
                fade = max(0.0, 1.0 - age / self.TRAIL_MAX_AGE)
                if fade <= 0.05:
                    continue
                width = max(1, int(4 * fade))   # thinner against white arms
                bg = C.INDUSTRIAL_FLOOR
                blended = tuple(
                    int(bg[k] + (trail_color[k] - bg[k]) * fade) for k in range(3)
                )
                with contextlib.suppress(pygame.error):
                    pygame.draw.line(
                        surface, blended,
                        (int(a.x), int(a.y)), (int(b.x), int(b.y)),
                        width,
                    )

        # Banners — ease in, hold, ease out.
        for b in self.banners:
            t = (now - b.born_at) / b.duration
            # Three-phase envelope: 0→0.15 ease-in, 0.15→0.75 hold, 0.75→1 ease-out.
            if t < 0.15:
                alpha = t / 0.15
                scale = 0.85 + 0.15 * alpha
            elif t > 0.75:
                alpha = (1 - t) / 0.25
                scale = 1.0 + 0.05 * (1 - alpha)
            else:
                alpha = 1.0
                scale = 1.0
            alpha = max(0.0, min(1.0, alpha))
            self._draw_banner(surface, b, alpha, scale, font_heading_path)

    def _draw_banner(
        self,
        surface: pygame.Surface,
        b: Banner,
        alpha: float,
        scale: float,
        font_heading_path: str,
    ) -> None:
        base_size = int(68 * scale)
        font = pygame.font.Font(font_heading_path, base_size)
        text_surf = font.render(b.text, True, b.color)
        tw, th = text_surf.get_size()

        # Background stripe spanning the main viewport.
        y_center = C.HEADER_HEIGHT + 70 if b.y_band == 0 else C.HEIGHT - C.FOOTER_HEIGHT - 100
        stripe_h = th + 28
        stripe = pygame.Surface((C.VIEWPORT_WIDTH, stripe_h), pygame.SRCALPHA)
        stripe.fill((*C.PAPER, int(230 * alpha)))
        # Bold accent underline.
        pygame.draw.rect(stripe, (*b.color, int(200 * alpha)),
                         (0, stripe_h - 6, C.VIEWPORT_WIDTH, 6))
        surface.blit(stripe, (0, y_center - stripe_h // 2))

        # Center the text inside the stripe.
        text_surf.set_alpha(int(255 * alpha))
        surface.blit(text_surf,
                     (C.VIEWPORT_WIDTH // 2 - tw // 2, y_center - th // 2))
