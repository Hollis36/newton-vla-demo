"""Unit tests for the voice fuzzy-match post-processor.

These tests don't touch the mic or network — they exercise fuzzy_snap()
on pre-recorded noisy transcripts to verify the phonetic correction table
and difflib fallback behave as advertised.
"""

from __future__ import annotations

import unittest

from demo_live.voice import fuzzy_snap


class PhoneticTableTest(unittest.TestCase):
    """Hand-tuned 1:1 replacements must survive fuzzy_snap unchanged."""

    def test_peter_to_pick(self) -> None:
        self.assertEqual(fuzzy_snap("peter"), "pick")

    def test_ride_to_red(self) -> None:
        self.assertEqual(fuzzy_snap("ride"), "red")

    def test_flower_to_tower(self) -> None:
        self.assertEqual(fuzzy_snap("flower"), "tower")

    def test_peter_ride_to_pick_red(self) -> None:
        """Common Google Speech mishear for 'pick red'."""
        self.assertEqual(fuzzy_snap("peter ride"), "pick red")

    def test_compound_command(self) -> None:
        self.assertEqual(
            fuzzy_snap("peter the grain block"),
            "pick the green block",
        )


class ExactVocabTest(unittest.TestCase):
    """Already-correct words should pass through identically."""

    def test_vocab_word_unchanged(self) -> None:
        for w in ("pick", "red", "stack", "tower"):
            self.assertEqual(fuzzy_snap(w), w)

    def test_clean_sentence_unchanged(self) -> None:
        self.assertEqual(
            fuzzy_snap("pick up the red block"),
            "pick up the red block",
        )


class FillerFilterTest(unittest.TestCase):
    """Post-B5 research finding: fuzzy_snap must drop pure disfluencies
    before the phonetic stage, otherwise they pollute downstream parsing.
    See research/voice_correction/REPORT_W1.md §4.3."""

    def test_um_is_dropped(self) -> None:
        self.assertEqual(fuzzy_snap("pick um red"), "pick red")

    def test_uh_is_dropped(self) -> None:
        self.assertEqual(fuzzy_snap("uh stack red green"), "stack red green")

    def test_like_is_dropped(self) -> None:
        self.assertEqual(fuzzy_snap("like pick red"), "pick red")

    def test_multiple_fillers_dropped(self) -> None:
        self.assertEqual(fuzzy_snap("um like pick uh red"), "pick red")

    def test_article_is_preserved(self) -> None:
        """Articles are NOT filler — parser context uses them."""
        out = fuzzy_snap("pick the red block")
        self.assertIn("the", out.split())


class FuzzyMatchTest(unittest.TestCase):
    """Words not in the phonetic table but close to vocab should snap."""

    def test_edit_distance_snaps_near_vocab(self) -> None:
        """`stac` is one char off from `stack` — low cutoff should snap."""
        out = fuzzy_snap("stac", cutoff=0.5)
        self.assertIn("stack", out.split(),
                      msg=f"expected 'stac' to fuzzy-snap to 'stack', got {out!r}")

    def test_punctuation_stripped(self) -> None:
        self.assertIn("red", fuzzy_snap("ride!"))

    def test_case_folded(self) -> None:
        self.assertEqual(fuzzy_snap("PETER"), "pick")

    def test_fully_unknown_passes_through(self) -> None:
        """A word with no close match should not be corrupted."""
        out = fuzzy_snap("xyzzyq", cutoff=0.9)
        self.assertIn("xyzzyq", out.split())


class VocabFirstDispatchTest(unittest.TestCase):
    """B7 dispatch trusts in-vocab tokens. Regression-tests the prior
    bug where directional words got phonetic-mapped before the vocab
    check — `drive left` used to become `drive pick`."""

    def test_drive_left_stays_drive_left(self) -> None:
        """Direction word must not be phonetic-mapped to 'pick'."""
        self.assertEqual(fuzzy_snap("drive left"), "drive left")

    def test_drive_right_stays(self) -> None:
        self.assertEqual(fuzzy_snap("drive right"), "drive right")

    def test_lift_stays_lift(self) -> None:
        """Parser keyword fallback maps lift→pick at parse time; voice
        layer no longer has to pre-normalize it."""
        self.assertEqual(
            fuzzy_snap("lift the green block"),
            "lift the green block",
        )


class BigramRerankTest(unittest.TestCase):
    """When difflib returns multiple candidates, bigram LM context
    should pick the contextually-correct one over the highest-ratio one."""

    def test_rate_in_context_becomes_red(self) -> None:
        """`the rate block` — difflib gives {red, reset, rest}; LM picks red."""
        out = fuzzy_snap("the rate block")
        self.assertIn("red", out.split(),
                      msg=f"expected 'rate' between 'the' and 'block' to "
                          f"rerank to 'red', got {out!r}")

    def test_aggressive_mispronunciation_recovers(self) -> None:
        """Non-native speaker's `staaack the bloo` should still parse."""
        out = fuzzy_snap("staaack the bloo")
        self.assertIn("stack", out.split())
        self.assertIn("blue", out.split())


if __name__ == "__main__":
    unittest.main()
