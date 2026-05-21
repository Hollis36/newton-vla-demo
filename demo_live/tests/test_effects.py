"""Unit tests for `demo_live.effects.EffectsLayer`.

EffectsLayer is the visual-reward layer: particle bursts, expanding rings,
banner text, motion trail. Each is short-lived and self-cleaning. The
render path is exercised by `test_render_smoke.py`; here we focus on the
state machine (emit, age, expire) so a regression in cleanup doesn't
silently leak unbounded particles across a 3-minute live demo.

A single shared pygame.init() / Surface keeps these tests fast (~5 ms).
"""

from __future__ import annotations

import os
import time
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from demo_live import config as C  # noqa: E402
from demo_live.effects import EffectsLayer  # noqa: E402


class _PygameHarness(unittest.TestCase):
    """Pygame init / Surface shared across all effect tests."""

    surface: pygame.Surface

    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        cls.surface = pygame.Surface((C.WIDTH, C.HEIGHT))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()


# ============================================================================
# burst()
# ============================================================================


class BurstTest(_PygameHarness):
    def test_emits_n_particles(self) -> None:
        layer = EffectsLayer()
        layer.burst((100, 100), count=10)
        self.assertEqual(len(layer.particles), 10)

    def test_burst_also_emits_one_ring(self) -> None:
        """burst() doubles as a ring emitter for the celebratory pulse."""
        layer = EffectsLayer()
        layer.burst((100, 100), count=4)
        self.assertEqual(len(layer.rings), 1)

    def test_particles_carry_provided_color(self) -> None:
        layer = EffectsLayer()
        layer.burst((50, 50), color=(255, 128, 0), count=3)
        for p in layer.particles:
            self.assertEqual(p.color, (255, 128, 0))

    def test_default_count_is_safe(self) -> None:
        """No args other than position — must not raise."""
        layer = EffectsLayer()
        layer.burst((50, 50))
        self.assertGreater(len(layer.particles), 0)


# ============================================================================
# ring()
# ============================================================================


class RingTest(_PygameHarness):
    def test_ring_does_not_emit_particles(self) -> None:
        """Unlike burst(), ring() is a standalone decision-moment cue."""
        layer = EffectsLayer()
        layer.ring((200, 200))
        self.assertEqual(len(layer.rings), 1)
        self.assertEqual(len(layer.particles), 0)

    def test_ring_uses_provided_max_radius(self) -> None:
        layer = EffectsLayer()
        layer.ring((100, 100), max_radius=150.0)
        self.assertEqual(layer.rings[0].max_radius, 150.0)

    def test_ring_expires_after_duration(self) -> None:
        layer = EffectsLayer()
        layer.ring((100, 100), duration=0.001)   # 1 ms — already over by next tick
        time.sleep(0.005)
        layer.update(1 / 60)
        self.assertEqual(len(layer.rings), 0)


# ============================================================================
# banner()
# ============================================================================


class BannerTest(_PygameHarness):
    def test_appends_banner(self) -> None:
        layer = EffectsLayer()
        layer.banner("HELLO", color=(255, 0, 0), duration=0.5)
        self.assertEqual(len(layer.banners), 1)
        self.assertEqual(layer.banners[0].text, "HELLO")

    def test_banner_expires(self) -> None:
        layer = EffectsLayer()
        layer.banner("X", duration=0.001)
        time.sleep(0.005)
        layer.update(1 / 60)
        self.assertEqual(len(layer.banners), 0)

    def test_multiple_banners_coexist(self) -> None:
        layer = EffectsLayer()
        layer.banner("A")
        layer.banner("B")
        self.assertEqual(len(layer.banners), 2)


# ============================================================================
# push_trail()
# ============================================================================


class TrailTest(_PygameHarness):
    def test_first_sample_always_added(self) -> None:
        layer = EffectsLayer()
        layer.push_trail((100.0, 100.0))
        self.assertEqual(len(layer.trail), 1)

    def test_duplicate_positions_dropped(self) -> None:
        """Two samples within TRAIL_MIN_DELTA of each other collapse to one
        — a stationary arm shouldn't bloat the trail."""
        layer = EffectsLayer()
        layer.push_trail((100.0, 100.0))
        layer.push_trail((100.5, 100.5))   # delta < TRAIL_MIN_DELTA=4
        self.assertEqual(len(layer.trail), 1)

    def test_distant_positions_appended(self) -> None:
        layer = EffectsLayer()
        layer.push_trail((100.0, 100.0))
        layer.push_trail((200.0, 100.0))   # 100 px apart, well above min delta
        self.assertEqual(len(layer.trail), 2)

    def test_trail_capped_at_max_samples(self) -> None:
        """Pushing more than TRAIL_MAX_SAMPLES discards the oldest."""
        layer = EffectsLayer()
        for i in range(layer.TRAIL_MAX_SAMPLES + 20):
            layer.push_trail((float(i * 10), 0.0))
        self.assertEqual(len(layer.trail), layer.TRAIL_MAX_SAMPLES)

    def test_trail_expires_with_age(self) -> None:
        """Samples older than TRAIL_MAX_AGE are pruned by update()."""
        layer = EffectsLayer()
        layer.push_trail((100.0, 100.0))
        # Backdate the sample so update() considers it expired.
        layer.trail[0].born_at = time.perf_counter() - (layer.TRAIL_MAX_AGE + 0.1)
        layer.update(1 / 60)
        self.assertEqual(len(layer.trail), 0)


# ============================================================================
# update()
# ============================================================================


class UpdateTest(_PygameHarness):
    def test_empty_layer_update_is_noop(self) -> None:
        layer = EffectsLayer()
        layer.update(1 / 60)   # must not raise

    def test_particles_age_and_prune(self) -> None:
        layer = EffectsLayer()
        layer.burst((100, 100), count=5)
        # Force-expire every particle.
        for p in layer.particles:
            p.life = -0.1
        layer.update(1 / 60)
        self.assertEqual(len(layer.particles), 0)
        # Ring should still be alive (its lifetime is independent).
        self.assertEqual(len(layer.rings), 1)

    def test_gravity_pulls_particles_down(self) -> None:
        layer = EffectsLayer()
        layer.burst((100, 100), count=1)
        original_vy = layer.particles[0].vy
        layer.update(1 / 60)
        # After one tick of gravity, vy must have increased (screen +y is down).
        self.assertGreater(layer.particles[0].vy, original_vy)


# ============================================================================
# draw() smoke
# ============================================================================


class DrawSmokeTest(_PygameHarness):
    """draw() reads from C.FONT_HEADING — make sure the full pipeline (all
    primitive types active) renders without raising."""

    def test_full_layer_draws_without_error(self) -> None:
        layer = EffectsLayer()
        layer.burst((100, 100), count=5)
        layer.ring((200, 200))
        layer.banner("TEST")
        layer.push_trail((300.0, 300.0))
        layer.push_trail((350.0, 300.0))
        layer.update(1 / 60)
        layer.draw(self.surface, C.FONT_HEADING)


if __name__ == "__main__":
    unittest.main()
