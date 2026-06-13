"""Unit tests for the learned intent-policy seam in `demo_live.policy`.

The real adapter (`TransformersZeroShotPolicy`) would pull in torch, so it is
not exercised here — we test the seam itself: the protocol, the deterministic
mock policy, the registry, and the `PolicyUnavailable` contract.
"""

from __future__ import annotations

import unittest
from unittest import mock

from demo_live import policy, vla


class MockLearnedPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = policy.MockLearnedPolicy()

    def test_satisfies_protocol(self) -> None:
        self.assertIsInstance(self.policy, policy.LearnedPolicy)

    def test_parses_english(self) -> None:
        data = self.policy.parse("pick up the red block")
        self.assertEqual(data["action"], "pick")
        self.assertEqual(data["color"], "red")
        self.assertIn("mock-learned", data["reason"])

    def test_parses_chinese(self) -> None:
        data = self.policy.parse("搭一个塔")
        self.assertEqual(data["action"], "stack")

    def test_returns_full_schema(self) -> None:
        data = self.policy.parse("dance for us")
        for key in ("action", "color", "colors", "target", "reason"):
            self.assertIn(key, data)


class RegistryTest(unittest.TestCase):
    def tearDown(self) -> None:
        # Reset the module singleton so tests don't leak into each other.
        policy._default_policy = None

    def test_default_is_mock(self) -> None:
        self.assertIsInstance(policy.get_default_policy(), policy.MockLearnedPolicy)

    def test_default_is_cached(self) -> None:
        self.assertIs(policy.get_default_policy(), policy.get_default_policy())

    def test_set_default_policy(self) -> None:
        sentinel = policy.MockLearnedPolicy()
        policy.set_default_policy(sentinel)
        self.assertIs(policy.get_default_policy(), sentinel)


class TransformersAdapterTest(unittest.TestCase):
    def test_raises_policy_unavailable_without_transformers(self) -> None:
        adapter = policy.TransformersZeroShotPolicy()
        with mock.patch.dict("sys.modules", {"transformers": None}), \
             self.assertRaises(policy.PolicyUnavailable):
            adapter._ensure_loaded()

    def test_action_labels_subset_of_known_actions(self) -> None:
        self.assertTrue(set(policy.ACTION_LABELS).issubset(set(vla.KNOWN_ACTIONS)))
        self.assertNotIn("unknown", policy.ACTION_LABELS)


class LearnedBackendIntegrationTest(unittest.TestCase):
    """The "learned" VLA backend should route through whatever policy is
    installed via `vla.set_learned_policy`, and fall back to keywords if the
    policy errors."""

    def tearDown(self) -> None:
        vla.set_learned_policy(None)
        policy._default_policy = None

    def test_uses_injected_policy(self) -> None:
        class _StubPolicy:
            name = "stub"

            def parse(self, user_input, world_state=None):
                return {"action": "home", "color": None, "colors": None,
                        "target": None, "reason": "stub home"}

        vla.set_learned_policy(_StubPolicy())
        r = vla.parse_command("anything at all", backend="learned")
        self.assertEqual(r.action, "home")
        self.assertEqual(r.source, "learned")

    def test_policy_error_falls_back_to_keyword(self) -> None:
        class _BoomPolicy:
            name = "boom"

            def parse(self, user_input, world_state=None):
                raise RuntimeError("model exploded")

        vla.set_learned_policy(_BoomPolicy())
        r = vla.parse_command("build a tower", backend="learned")
        self.assertEqual(r.action, "stack")
        self.assertEqual(r.source, "fallback")


if __name__ == "__main__":
    unittest.main()
