"""Render-layer smoke tests: assert the public draw_* surfaces from both
the industrial `scene` module and the legacy classroom `scene_legacy` module
can be called against a real World instance under SDL_VIDEODRIVER=dummy
without raising.

No pixel comparison — that's brittle to legitimate visual polish. The
purpose is to lock the *contract* (callable, accepts these args) so the
Phase B refactor can't silently break a public function signature.

EffectsLayer.update + draw are smoked here too so we catch font / pygame
init regressions in one place.

NOTE: all probes live in a single test class so pygame.init / pygame.quit
run exactly once. `render._FONT_CACHE` holds pygame.font.Font objects that
go invalid the moment pygame.quit() runs — splitting probes across multiple
TestCases with their own setUpClass/tearDownClass triggers
`pygame.error: Invalid font (font module quit since font created)` on the
second class.
"""

from __future__ import annotations

import os
import unittest

# Headless SDL MUST be set before pygame.init.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from demo_live import config as C  # noqa: E402
from demo_live import effects, scene, scene_legacy  # noqa: E402
from demo_live.physics import World  # noqa: E402


class RenderSmokeTest(unittest.TestCase):
    """Booted-once World + pygame Surface, shared across all draw_* probes.

    World() compiles or loads Warp kernels (~3 s cold, ~50 ms warm), so we
    pay that cost once per test class.
    """

    surface: pygame.Surface
    world: World

    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        cls.surface = pygame.Surface((C.WIDTH, C.HEIGHT))
        cls.world = World()
        # A few solver steps so arm_state_from_target returns sane numbers.
        for _ in range(5):
            cls.world.step()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    # ---- industrial scene.py ----

    def test_industrial_draw_ground(self) -> None:
        scene.draw_ground(self.surface)

    def test_industrial_draw_arm_base(self) -> None:
        scene.draw_arm_base(self.surface, self.world, mode_label="IDLE")

    def test_industrial_draw_arm(self) -> None:
        scene.draw_arm(self.surface, self.world, holding=False)

    def test_industrial_draw_arm_holding(self) -> None:
        scene.draw_arm(self.surface, self.world, holding=True)

    def test_industrial_draw_blocks(self) -> None:
        scene.draw_blocks(self.surface, self.world)

    def test_industrial_draw_ball(self) -> None:
        scene.draw_ball(self.surface, self.world)

    def test_industrial_draw_com_overlay(self) -> None:
        # Stable and unstable variants — the experiment's lecture overlay.
        scene.draw_com_overlay(self.surface, 2.05, 1.95, 2.15, True)
        scene.draw_com_overlay(self.surface, 1.90, 1.95, 2.15, False)

    def test_industrial_draw_header(self) -> None:
        scene.draw_header(self.surface, mode_label="IDLE", fps=60.0)

    def test_industrial_draw_side_panel(self) -> None:
        scene.draw_side_panel(
            self.surface,
            status_lines=["status row 1", "status row 2"],
            recent_commands=["pick red", "build a tower"],
            parsed_json={"action": "pick", "color": "red"},
        )

    def test_industrial_draw_footer_idle(self) -> None:
        scene.draw_footer(self.surface, prompt="Press 2 to talk",
                          input_text="", input_active=False)

    def test_industrial_draw_footer_thinking(self) -> None:
        scene.draw_footer(self.surface, prompt="Working…",
                          input_text="pick red",
                          input_active=True, thinking=True)

    # ---- legacy scene_legacy.py (default classroom whiteboard) ----

    def test_legacy_draw_ground(self) -> None:
        scene_legacy.draw_ground(self.surface)

    def test_legacy_draw_arm_base(self) -> None:
        scene_legacy.draw_arm_base(self.surface, self.world)

    def test_legacy_draw_arm(self) -> None:
        scene_legacy.draw_arm(self.surface, self.world, holding=False)

    def test_legacy_draw_arm_holding(self) -> None:
        scene_legacy.draw_arm(self.surface, self.world, holding=True)

    def test_legacy_draw_blocks(self) -> None:
        scene_legacy.draw_blocks(self.surface, self.world)

    def test_legacy_draw_ball(self) -> None:
        scene_legacy.draw_ball(self.surface, self.world)

    def test_legacy_draw_header(self) -> None:
        scene_legacy.draw_header(self.surface, mode_label="IDLE", fps=60.0)

    def test_legacy_draw_side_panel(self) -> None:
        scene_legacy.draw_side_panel(
            self.surface,
            status_lines=["row 1", "row 2"],
            recent_commands=["pick red"],
            parsed_json={"action": "pick"},
        )

    def test_legacy_draw_footer(self) -> None:
        scene_legacy.draw_footer(self.surface, prompt="Press 2",
                                 input_text="", input_active=False)

    # ---- effects layer ----

    def test_effects_empty_layer_update_and_draw(self) -> None:
        layer = effects.EffectsLayer()
        layer.update(1 / 60)
        layer.draw(self.surface, font_heading_path=C.FONT_HEADING)


if __name__ == "__main__":
    unittest.main()
