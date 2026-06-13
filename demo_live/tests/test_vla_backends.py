"""Unit tests for the modernized VLA backend layer in `demo_live.vla`:

  * `_extract_json_object` — the balanced-brace JSON scanner that replaced a
    greedy `\\{.*\\}` regex.
  * `_resolve_model_id` — alias → fully-qualified model id.
  * `_call_anthropic_api` — the Anthropic SDK / forced-tool-use path, mocked
    via an injected fake `anthropic` module (no SDK install, no network).
  * `parse_command(backend=...)` dispatch and the keyword/api safety nets.

The default ("cli") path is covered by test_vla_parser / test_vla_subprocess;
here we focus on what's new.
"""

from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from demo_live import vla

# ============================================================================
# Balanced JSON extraction
# ============================================================================


class ExtractJsonObjectTest(unittest.TestCase):
    def test_bare_object(self) -> None:
        self.assertEqual(vla._extract_json_object('{"action":"pick"}'), {"action": "pick"})

    def test_first_of_two_objects(self) -> None:
        """Greedy `\\{.*\\}` would merge both objects into invalid JSON; the
        balanced scanner returns just the first complete one."""
        self.assertEqual(
            vla._extract_json_object('{"action":"pick"} trailing {"x":1}'),
            {"action": "pick"},
        )

    def test_braces_inside_string_value(self) -> None:
        """A `}` inside a string must not close the object early."""
        self.assertEqual(
            vla._extract_json_object('{"reason":"go to {the left}","action":"home"}'),
            {"reason": "go to {the left}", "action": "home"},
        )

    def test_object_with_prose_around_it(self) -> None:
        chatty = 'Sure! {"action":"drive","target":[1.0,0]} hope that helps'
        self.assertEqual(
            vla._extract_json_object(chatty),
            {"action": "drive", "target": [1.0, 0]},
        )

    def test_no_brace_returns_none(self) -> None:
        self.assertIsNone(vla._extract_json_object("no json here"))

    def test_malformed_returns_none(self) -> None:
        self.assertIsNone(vla._extract_json_object("{action: pick}"))

    def test_non_object_json_returns_none(self) -> None:
        """A balanced `{...}` that parses to a non-dict is rejected."""
        self.assertIsNone(vla._extract_json_object("[1, 2, 3]"))


# ============================================================================
# Model alias resolution
# ============================================================================


class ResolveModelIdTest(unittest.TestCase):
    def test_known_aliases(self) -> None:
        self.assertEqual(vla._resolve_model_id("sonnet"), "claude-sonnet-4-6")
        self.assertEqual(vla._resolve_model_id("haiku"), "claude-haiku-4-5")
        self.assertEqual(vla._resolve_model_id("opus"), "claude-opus-4-8")

    def test_full_id_passthrough(self) -> None:
        self.assertEqual(vla._resolve_model_id("claude-opus-4-8"), "claude-opus-4-8")
        self.assertEqual(vla._resolve_model_id("some-future-model"), "some-future-model")


# ============================================================================
# Anthropic API backend (mocked SDK)
# ============================================================================


class _FakeBlock(SimpleNamespace):
    pass


def _install_fake_anthropic(test: unittest.TestCase, *, response=None, raises=None) -> dict:
    """Inject a fake `anthropic` module into sys.modules for the duration of
    a test. Returns a dict that captures the kwargs passed to
    `messages.create` so callers can assert on them."""
    captured: dict = {}

    class _FakeMessages:
        def create(self, **kwargs):
            captured["create_kwargs"] = kwargs
            if raises is not None:
                raise raises
            return response

    class _FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.messages = _FakeMessages()

    fake_module = SimpleNamespace(Anthropic=_FakeClient)
    patcher = mock.patch.dict(sys.modules, {"anthropic": fake_module})
    patcher.start()
    test.addCleanup(patcher.stop)
    return captured


class AnthropicApiBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"})
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_happy_path_returns_tool_input(self) -> None:
        response = SimpleNamespace(content=[
            _FakeBlock(type="text", text="thinking..."),
            _FakeBlock(type="tool_use", name="emit_robot_action",
                       input={"action": "pick", "color": "red", "reason": "ok"}),
        ])
        captured = _install_fake_anthropic(self, response=response)
        out = vla._call_anthropic_api("pick the red block", model="haiku")
        self.assertEqual(out, {"action": "pick", "color": "red", "reason": "ok"})
        # Forced tool use + cache-marked system prompt + resolved model id.
        kw = captured["create_kwargs"]
        self.assertEqual(kw["tool_choice"], {"type": "tool", "name": "emit_robot_action"})
        self.assertEqual(kw["model"], "claude-haiku-4-5")
        self.assertEqual(kw["system"][0]["cache_control"], {"type": "ephemeral"})

    def test_no_tool_use_block_returns_none(self) -> None:
        response = SimpleNamespace(content=[_FakeBlock(type="text", text="nope")])
        _install_fake_anthropic(self, response=response)
        self.assertIsNone(vla._call_anthropic_api("pick red"))

    def test_sdk_exception_returns_none(self) -> None:
        _install_fake_anthropic(self, raises=RuntimeError("network down"))
        self.assertIsNone(vla._call_anthropic_api("pick red"))

    def test_missing_api_key_returns_none(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            # Even with the fake module present, no key → short-circuit.
            _install_fake_anthropic(self, response=SimpleNamespace(content=[]))
            self.assertIsNone(vla._call_anthropic_api("pick red"))

    def test_missing_sdk_returns_none(self) -> None:
        # Force `import anthropic` to fail.
        with mock.patch.dict(sys.modules, {"anthropic": None}):
            self.assertIsNone(vla._call_anthropic_api("pick red"))


# ============================================================================
# Backend dispatch in parse_command
# ============================================================================


class ParseCommandDispatchTest(unittest.TestCase):
    def test_keyword_backend_is_deterministic_offline(self) -> None:
        r = vla.parse_command("build a tower", backend="keyword")
        self.assertEqual(r.action, "stack")
        self.assertEqual(r.source, "fallback")

    def test_api_backend_falls_back_to_keyword_without_key(self) -> None:
        with mock.patch.object(vla, "_call_anthropic_api", return_value=None):
            r = vla.parse_command("pick the green block", backend="api")
        self.assertEqual(r.action, "pick")
        self.assertEqual(r.color, "green")
        self.assertEqual(r.source, "fallback")

    def test_api_backend_uses_api_source_on_success(self) -> None:
        with mock.patch.object(
            vla, "_call_anthropic_api",
            return_value={"action": "home", "color": None, "colors": None,
                          "target": None, "reason": "k"},
        ):
            r = vla.parse_command("go home", backend="api")
        self.assertEqual(r.action, "home")
        self.assertEqual(r.source, "api")

    def test_learned_backend_uses_mock_policy(self) -> None:
        r = vla.parse_command("拿起红色方块", backend="learned")
        self.assertEqual(r.action, "pick")
        self.assertEqual(r.color, "red")
        self.assertEqual(r.source, "learned")

    def test_default_backend_calls_cli(self) -> None:
        """Backend defaulting must keep routing through `_call_claude_cli`
        so the existing test mocks of that symbol keep working."""
        with mock.patch.object(vla, "DEFAULT_BACKEND", "cli"), \
             mock.patch.object(vla, "_call_claude_cli", return_value=None) as cli:
            vla.parse_command("pick red")
        cli.assert_called_once()

    def test_backend_override_via_default_constant(self) -> None:
        with mock.patch.object(vla, "DEFAULT_BACKEND", "keyword"):
            r = vla.parse_command("dance for us")
        self.assertEqual(r.action, "dance")
        self.assertEqual(r.source, "fallback")


if __name__ == "__main__":
    unittest.main()
