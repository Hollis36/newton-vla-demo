"""Display-mode defaults for the live demo."""

from __future__ import annotations

import unittest

from demo_live.__main__ import parse_args


class DisplayModeArgsTest(unittest.TestCase):
    def test_default_display_mode_is_whiteboard(self) -> None:
        args = parse_args([])

        self.assertFalse(args.industrial)

    def test_industrial_flag_enables_industrial_mode(self) -> None:
        args = parse_args(["--industrial"])

        self.assertTrue(args.industrial)


if __name__ == "__main__":
    unittest.main()
