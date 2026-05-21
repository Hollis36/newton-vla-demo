"""Unit tests for the VLA keyword fallback parser.

The Claude CLI path is monkey-patched to always fail, so these tests exercise
the deterministic rule-based parser that must remain 100% reliable for the
offline-safety story.
"""

from __future__ import annotations

import unittest
from unittest import mock

from demo_live import vla


def _parse_offline(text: str) -> vla.VLAResult:
    """parse_command() with Claude CLI forced off — exercises the fallback."""
    with mock.patch.object(vla, "_call_claude_cli", return_value=None):
        return vla.parse_command(text, timeout=0.0)


class EnglishKeywordTest(unittest.TestCase):
    def test_pick_red(self) -> None:
        r = _parse_offline("pick up the red block")
        self.assertEqual(r.action, "pick")
        self.assertEqual(r.color, "red")
        self.assertEqual(r.source, "fallback")

    def test_stack_tower_defaults_to_rgb(self) -> None:
        r = _parse_offline("build a tower")
        self.assertEqual(r.action, "stack")
        self.assertEqual(r.colors, ["red", "green", "blue"])

    def test_stack_with_specific_colors(self) -> None:
        r = _parse_offline("stack red and blue")
        self.assertEqual(r.action, "stack")
        self.assertIn("red", r.colors)
        self.assertIn("blue", r.colors)

    def test_place_left(self) -> None:
        r = _parse_offline("put it on the left")
        self.assertEqual(r.action, "place")
        self.assertIsNotNone(r.target)
        self.assertLess(r.target[0], 0)

    def test_place_right(self) -> None:
        r = _parse_offline("put it on the right")
        self.assertEqual(r.action, "place")
        self.assertGreater(r.target[0], 0)

    def test_drive_right(self) -> None:
        r = _parse_offline("drive right")
        self.assertEqual(r.action, "drive")
        self.assertGreater(r.target[0], 0)

    def test_drive_to_color(self) -> None:
        """`go to the blue block` should drive toward blue's known x."""
        r = _parse_offline("drive to the blue block")
        self.assertEqual(r.action, "drive")
        # Blue sits near x=1.3; target should be positive and under 1.6.
        self.assertGreater(r.target[0], 0.5)
        self.assertLessEqual(r.target[0], 1.6)

    def test_home_keyword(self) -> None:
        r = _parse_offline("go home")
        self.assertEqual(r.action, "home")

    def test_reset_keyword(self) -> None:
        r = _parse_offline("reset")
        self.assertEqual(r.action, "home")

    def test_unknown_returns_unknown(self) -> None:
        r = _parse_offline("sdfjklsdfjkl")
        self.assertEqual(r.action, "unknown")

    def test_wave_gesture(self) -> None:
        for prompt in ("wave", "say hi", "please wave at us"):
            r = _parse_offline(prompt)
            self.assertEqual(r.action, "wave", prompt)

    def test_point_direction_default(self) -> None:
        r = _parse_offline("point at something")
        self.assertEqual(r.action, "point")
        self.assertEqual(r.colors, ["left"])

    def test_point_right(self) -> None:
        r = _parse_offline("point right")
        self.assertEqual(r.action, "point")
        self.assertEqual(r.colors, ["right"])

    def test_point_audience(self) -> None:
        r = _parse_offline("point at the audience")
        self.assertEqual(r.action, "point")
        self.assertEqual(r.colors, ["audience"])

    def test_bow(self) -> None:
        r = _parse_offline("take a bow")
        self.assertEqual(r.action, "bow")

    def test_dance(self) -> None:
        r = _parse_offline("dance for us")
        self.assertEqual(r.action, "dance")


class ChineseKeywordTest(unittest.TestCase):
    def test_pick_red_chinese(self) -> None:
        r = _parse_offline("拿起红色方块")
        self.assertEqual(r.action, "pick")
        self.assertEqual(r.color, "red")

    def test_stack_tower_chinese(self) -> None:
        r = _parse_offline("搭一个塔")
        self.assertEqual(r.action, "stack")

    def test_place_left_chinese(self) -> None:
        r = _parse_offline("把蓝色方块放到左边")
        self.assertEqual(r.action, "place")
        self.assertEqual(r.color, "blue")
        self.assertLess(r.target[0], 0)

    def test_drive_right_chinese(self) -> None:
        r = _parse_offline("往右走")
        self.assertEqual(r.action, "drive")
        self.assertGreater(r.target[0], 0)

    def test_home_chinese(self) -> None:
        r = _parse_offline("回位")
        self.assertEqual(r.action, "home")


class FieldSanitizationTest(unittest.TestCase):
    """parse_command must always return a well-typed VLAResult."""

    def test_result_fields_always_typed(self) -> None:
        r = _parse_offline("pick red")
        self.assertIsInstance(r.action, str)
        self.assertIn(r.action, {"pick", "place", "stack", "drive", "home", "unknown"})
        self.assertTrue(r.color is None or isinstance(r.color, str))
        self.assertTrue(r.colors is None or isinstance(r.colors, list))
        self.assertTrue(r.target is None or len(r.target) == 2)
        self.assertIsInstance(r.latency_ms, float)
        self.assertIn(r.source, {"claude", "fallback"})

    def test_invalid_colors_filtered_out(self) -> None:
        """If the parser output includes a bogus color, it should be dropped."""
        with mock.patch.object(
            vla, "_call_claude_cli",
            return_value={
                "action": "stack",
                "color": None,
                "colors": ["red", "not_a_color", "blue"],
                "target": None,
                "reason": "test",
            },
        ):
            r = vla.parse_command("stack", timeout=0.0)
        self.assertEqual(r.colors, ["red", "blue"])

    def test_invalid_action_becomes_unknown(self) -> None:
        with mock.patch.object(
            vla, "_call_claude_cli",
            return_value={"action": "EXPLODE", "color": None,
                          "colors": None, "target": None, "reason": ""},
        ):
            r = vla.parse_command("anything", timeout=0.0)
        self.assertEqual(r.action, "unknown")


if __name__ == "__main__":
    unittest.main()
