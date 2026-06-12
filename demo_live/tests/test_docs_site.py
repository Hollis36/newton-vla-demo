"""Pins docs/index.html (the GitHub Pages landing site) to the repo's
ground truth so the site can never silently drift from the README again,
and enforces the redesign's hard constraints (no lab affiliation text,
JS weight budget, scenes present with static fallbacks)."""

from __future__ import annotations

import gzip
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class DocsSiteParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(DOCS / "index.html")
        cls.readme = _read(ROOT / "README.md")

    def test_test_count_matches_readme_badge(self):
        badge = re.search(r"tests-(\d+)%20passing", self.readme)
        self.assertIsNotNone(badge, "README test badge missing")
        self.assertIn(f">{badge.group(1)}<", self.html,
                      "landing page test count must equal README badge")

    def test_version_matches_package(self):
        from demo_live import __version__
        self.assertIn(f"REV {__version__}", self.html)

    def test_line_count_matches_readme_badge(self):
        badge = re.search(r"code-(\d+)%20lines", self.readme)
        self.assertIsNotNone(badge)
        self.assertIn(badge.group(1), self.html)

    def test_no_lab_affiliation_anywhere(self):
        for needle in ("Xidian", "State Key", "Electromechanical Integrated",
                       "重点实验室", "西安电子"):
            self.assertNotIn(needle, self.html,
                             f"affiliation text {needle!r} must not appear")

    def test_blueprint_chapter_markers_present(self):
        for sht in ("SHT 01", "SHT 02", "SHT 03", "SHT 04", "SHT 05"):
            self.assertIn(sht, self.html)

    def test_scene_canvases_and_fallbacks_present(self):
        for scene_id in ("hero-scene", "lab-scene"):
            self.assertIn(f'id="{scene_id}"', self.html)
            self.assertIn(f'id="{scene_id}-fallback"', self.html)

    def test_reduced_motion_media_query_present(self):
        self.assertIn("prefers-reduced-motion", self.html)


class DocsSiteAssetBudgetTest(unittest.TestCase):
    def test_js_bundle_under_100kb_gzip(self):
        total = 0
        for name in ("matter.min.js", "hero.js", "lab.js"):
            p = DOCS / "assets" / name
            self.assertTrue(p.exists(), f"missing docs/assets/{name}")
            total += len(gzip.compress(p.read_bytes()))
        self.assertLess(total, 100 * 1024,
                        f"JS budget exceeded: {total / 1024:.0f} KB gzip")

    def test_experiment_figures_present_and_small(self):
        for name in ("experiment_aligned.png", "experiment_offset.png",
                     "experiment_topple.png"):
            p = DOCS / "figures" / name
            self.assertTrue(p.exists(), f"missing docs/figures/{name}")
            self.assertLess(p.stat().st_size, 350 * 1024,
                            f"{name} over 350 KB; downscale it")


if __name__ == "__main__":
    unittest.main()
