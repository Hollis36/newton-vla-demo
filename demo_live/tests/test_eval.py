"""Unit tests for the VLA evaluation harness in `demo_live.eval`.

The headline test is `test_keyword_backend_scores_100pct`: the curated
golden set is the contract for the deterministic parser, so any regression
that drops a rehearsed command turns this red.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from demo_live import eval as veval
from demo_live.vla import KNOWN_ACTIONS, VLAResult


class GoldenSetTest(unittest.TestCase):
    def test_keyword_backend_scores_100pct(self) -> None:
        report = veval.evaluate("keyword")
        self.assertEqual(
            report.accuracy, 1.0,
            "keyword parser regressed on golden set: "
            + "; ".join(f"{r.case.utterance!r}: {r.detail}" for r in report.failures),
        )

    def test_every_action_label_is_covered(self) -> None:
        covered = {c.action for c in veval.GOLD}
        self.assertEqual(covered, set(KNOWN_ACTIONS), "golden set must exercise every action")

    def test_gold_actions_are_valid(self) -> None:
        for case in veval.GOLD:
            self.assertIn(case.action, KNOWN_ACTIONS, case.utterance)


class CheckCaseTest(unittest.TestCase):
    def _result(self, **kw) -> VLAResult:
        base = dict(action="pick", color=None, colors=None, target=None,
                    reason="", source="fallback", latency_ms=0.0)
        base.update(kw)
        return VLAResult(**base)

    def test_action_mismatch_fails(self) -> None:
        case = veval.GoldCase("x", "stack")
        ok, _ = veval.check_case(case, self._result(action="pick"))
        self.assertFalse(ok)

    def test_color_checked_only_when_expected(self) -> None:
        case = veval.GoldCase("x", "pick")  # color None → not checked
        ok, _ = veval.check_case(case, self._result(action="pick", color="green"))
        self.assertTrue(ok)
        case2 = veval.GoldCase("x", "pick", color="red")
        ok2, _ = veval.check_case(case2, self._result(action="pick", color="green"))
        self.assertFalse(ok2)

    def test_target_sign_checked(self) -> None:
        case = veval.GoldCase("x", "drive", target_sign=-1)
        ok, _ = veval.check_case(case, self._result(action="drive", target=(-0.7, 0.0)))
        self.assertTrue(ok)
        ok2, _ = veval.check_case(case, self._result(action="drive", target=(0.7, 0.0)))
        self.assertFalse(ok2)

    def test_target_sign_requires_target(self) -> None:
        case = veval.GoldCase("x", "drive", target_sign=1)
        ok, detail = veval.check_case(case, self._result(action="drive", target=None))
        self.assertFalse(ok)
        self.assertIn("None", detail)

    def test_colors_tuple_compared(self) -> None:
        case = veval.GoldCase("x", "stack", colors=("red", "blue"))
        ok, _ = veval.check_case(case, self._result(action="stack", colors=["red", "blue"]))
        self.assertTrue(ok)


class ReportAndMainTest(unittest.TestCase):
    def test_report_stats(self) -> None:
        report = veval.evaluate("keyword")
        self.assertEqual(report.total, len(veval.GOLD))
        self.assertEqual(report.passed, report.total)
        self.assertEqual(report.failures, [])

    def test_main_keyword_exit_zero(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = veval.main(["--backend", "keyword"])
        self.assertEqual(code, 0)
        self.assertIn("accuracy", buf.getvalue())

    def test_main_json_output(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = veval.main(["--backend", "keyword", "--json"])
        self.assertEqual(code, 0)
        self.assertIn('"accuracy"', buf.getvalue())

    def test_main_min_accuracy_gate(self) -> None:
        """An impossible threshold fails even a perfect run."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = veval.main(["--backend", "keyword", "--min-accuracy", "1.01"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
