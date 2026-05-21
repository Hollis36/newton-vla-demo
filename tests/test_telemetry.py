"""Unit tests for `demo_live.telemetry`.

The logger is critical-path safe (never crashes the demo) but its on-disk
output is what an instructor relies on after class — these tests lock in
the CSV schema and the summary string format.
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from demo_live import telemetry


class CsvWritingTest(unittest.TestCase):
    def test_writes_header_and_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.csv"
            tele = telemetry.TelemetryLogger(path=path)
            tele.event("mode", detail="ball_catch")
            tele.event("vla", user_input="pick red",
                       parsed_action="pick", latency_ms=812.0,
                       backend="claude", success=True, detail="red")
            tele.close()

            with path.open(encoding="utf-8") as fp:
                rows = list(csv.reader(fp))
            self.assertEqual(rows[0], list(telemetry.COLUMNS))
            self.assertEqual(len(rows), 3)            # header + 2 rows
            # mode row
            self.assertEqual(rows[1][1], "mode")
            self.assertEqual(rows[1][-1], "ball_catch")
            # vla row carries latency + backend + success
            self.assertEqual(rows[2][1], "vla")
            self.assertEqual(rows[2][2], "pick red")
            self.assertEqual(rows[2][3], "pick")
            self.assertEqual(rows[2][4], "812.0")
            self.assertEqual(rows[2][5], "claude")
            self.assertEqual(rows[2][6], "1")

    def test_close_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.csv"
            tele = telemetry.TelemetryLogger(path=path)
            tele.event("mode")
            first = tele.close()
            second = tele.close()
            self.assertIsNotNone(first)
            self.assertIsNone(second)

    def test_event_after_close_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.csv"
            tele = telemetry.TelemetryLogger(path=path)
            tele.event("mode")
            tele.close()
            # Should not raise, just no-op.
            tele.event("vla", user_input="ignored")


class SanitizeTest(unittest.TestCase):
    def test_strips_newlines(self) -> None:
        self.assertEqual(telemetry._sanitize("hello\nworld"), "hello world")
        self.assertEqual(telemetry._sanitize("a\r\nb"), "a  b")

    def test_truncates_long_input(self) -> None:
        s = "x" * 500
        self.assertEqual(len(telemetry._sanitize(s)), 200)

    def test_empty_pass_through(self) -> None:
        self.assertEqual(telemetry._sanitize(""), "")

    def test_neutralizes_formula_prefixes(self) -> None:
        """A field starting with =, +, -, @, or \\t would be evaluated as
        a formula when an instructor opens the CSV in Excel. We prepend a
        single quote to force text mode."""
        for malicious in ("=1+1", "+cmd", "-2", "@SUM(A1)", "\tinjected"):
            sanitized = telemetry._sanitize(malicious)
            self.assertTrue(
                sanitized.startswith("'"),
                f"{malicious!r} → {sanitized!r} should start with single quote",
            )

    def test_passes_innocent_text_unchanged(self) -> None:
        for ok in ("pick red", "build a tower", "拿起红色方块"):
            self.assertEqual(telemetry._sanitize(ok), ok)


class SummaryTest(unittest.TestCase):
    def test_summary_counts_vla_and_catches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.csv"
            tele = telemetry.TelemetryLogger(path=path)
            tele.event("vla", parsed_action="pick", latency_ms=100.0,
                       backend="claude", success=True)
            tele.event("vla", parsed_action="stack", latency_ms=200.0,
                       backend="fallback", success=True)
            tele.event("catch", success=True)
            tele.event("catch", success=False)
            _, summary = tele.close()
            self.assertIn("VLA: 2", summary)
            self.assertIn("avg 150ms", summary)
            self.assertIn("1 fallback", summary)
            self.assertIn("catches: 1/2", summary)


class DefaultPathTest(unittest.TestCase):
    def test_default_path_under_logs(self) -> None:
        p = telemetry.default_path()
        self.assertEqual(p.parent.name, "logs")
        self.assertTrue(p.name.startswith("demo-"))
        self.assertTrue(p.name.endswith(".csv"))


if __name__ == "__main__":
    unittest.main()
