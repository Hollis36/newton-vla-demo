"""Pins docs/index.html (the GitHub Pages landing site) to the repo's
ground truth — README badges and the package version — so the site can
never silently drift again, and enforces publishing constraints:
absolute social-card URLs, referenced assets exist on disk, the v0.2.0
features are actually presented, and no lab affiliation text appears."""

from __future__ import annotations

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
        count = badge.group(1)
        self.assertIn(f"{count} tests", self.html,
                      "hero eyebrow test count must equal README badge")
        self.assertIn(f'<div class="num">{count}</div>', self.html,
                      "stats grid test count must equal README badge")

    def test_fps_matches_readme_badge(self):
        badge = re.search(r"fps-(\d+\.\d+)%20avg", self.readme)
        self.assertIsNotNone(badge, "README fps badge missing")
        fps = badge.group(1)
        self.assertIn(f"{fps} fps", self.html,
                      "hero eyebrow fps must equal README badge")
        self.assertIn(f'<div class="num">{fps}<span class="unit">fps',
                      self.html, "stats grid fps must equal README badge")

    def test_version_matches_package(self):
        from demo_live import __version__
        self.assertIn(f"v{__version__}", self.html,
                      "hero eyebrow version must equal demo_live.__version__")

    def test_pyproject_version_matches_package(self):
        from demo_live import __version__
        pyproject = _read(ROOT / "pyproject.toml")
        match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml version missing")
        self.assertEqual(match.group(1), __version__,
                         "pyproject.toml must match demo_live.__version__")

    def test_social_card_urls_are_absolute(self):
        for prop in ("og:image", "twitter:image"):
            meta = re.search(
                rf'(?:property|name)="{prop}" content="([^"]+)"', self.html)
            self.assertIsNotNone(meta, f"{prop} meta tag missing")
            self.assertTrue(
                meta.group(1).startswith("https://"),
                f"{prop} must be an absolute URL for social crawlers, "
                f"got {meta.group(1)!r}")

    def test_referenced_figures_exist(self):
        refs = set(re.findall(r'(?:src|href|poster)="(figures/[^"]+)"',
                              self.html))
        self.assertTrue(refs, "no figure references found in index.html")
        for ref in sorted(refs):
            self.assertTrue((DOCS / ref).is_file(),
                            f"index.html references missing file {ref}")

    def test_local_doc_links_exist(self):
        for name in ("report.pdf", "slides.pdf"):
            self.assertIn(f'href="{name}"', self.html)
            self.assertTrue((DOCS / name).is_file(),
                            f"docs/{name} linked but missing")

    def test_v020_features_are_presented(self):
        for needle in ("The physics got real", "--real-blocks",
                       "make collab", "make experiment", "6.7"):
            self.assertIn(needle, self.html,
                          f"v0.2.0 feature {needle!r} absent from the page")

    def test_no_lab_affiliation_anywhere(self):
        for needle in ("Xidian", "State Key", "Electromechanical Integrated",
                       "重点实验室", "西安电子"):
            self.assertNotIn(needle, self.html,
                             f"affiliation text {needle!r} must not appear")


class DocsSiteAssetTest(unittest.TestCase):
    def test_feature_figures_present_and_small(self):
        for name in ("experiment_aligned.png", "experiment_offset.png",
                     "experiment_topple.png", "collab_relay.png"):
            p = DOCS / "figures" / name
            self.assertTrue(p.exists(), f"missing docs/figures/{name}")
            self.assertLess(p.stat().st_size, 350 * 1024,
                            f"{name} over 350 KB; downscale it")


if __name__ == "__main__":
    unittest.main()
