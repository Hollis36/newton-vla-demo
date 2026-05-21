"""Unit tests for `demo_live.vla._call_claude_cli` — the subprocess path.

`_call_claude_cli` shells out to `claude --print` and parses its JSON.
The contract is: return `dict` on success, return `None` on ANY failure
(CLI missing, subprocess timeout, exit code ignored, no JSON in stdout,
JSON parse error). The caller (`parse_command`) treats `None` as "fall
back to the keyword parser" — the demo's live-safety story depends on
that being airtight.

We mock `subprocess.run` and `shutil.which` so the tests don't actually
invoke the Claude CLI.
"""

from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from demo_live import vla


def _mock_run_returning(stdout: str, *, returncode: int = 0) -> mock.MagicMock:
    """Build a subprocess.run mock that yields a CompletedProcess-like."""
    return mock.MagicMock(
        return_value=SimpleNamespace(
            stdout=stdout,
            stderr="",
            returncode=returncode,
        )
    )


# ============================================================================
# CLI availability gating
# ============================================================================


class CliMissingTest(unittest.TestCase):
    def test_returns_none_when_claude_not_on_path(self) -> None:
        """If `claude` isn't installed, `_call_claude_cli` must short-circuit
        to None — the keyword fallback handles every demo command on its own."""
        with mock.patch.object(vla.shutil, "which", return_value=None):
            self.assertIsNone(vla._call_claude_cli("pick red"))

    def test_no_subprocess_run_when_claude_missing(self) -> None:
        """When `claude` is missing we shouldn't even attempt to spawn a
        process — otherwise an audience laptop without Claude installed
        leaks a 5-10s startup stall per command."""
        with mock.patch.object(vla.shutil, "which", return_value=None), \
             mock.patch.object(vla.subprocess, "run") as fake_run:
            vla._call_claude_cli("pick red")
            fake_run.assert_not_called()


# ============================================================================
# Happy path — well-formed JSON in stdout
# ============================================================================


class HappyPathTest(unittest.TestCase):
    def test_parses_bare_json(self) -> None:
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(
                vla.subprocess, "run",
                _mock_run_returning('{"action":"pick","color":"red","colors":null,"target":null,"reason":"ok"}'),
        ):
            result = vla._call_claude_cli("pick red")
        self.assertEqual(result, {
            "action": "pick", "color": "red",
            "colors": None, "target": None, "reason": "ok",
        })

    def test_strips_markdown_fence(self) -> None:
        """Claude occasionally wraps its output in ```json ... ``` despite
        the prompt saying 'No markdown fences.' We strip them."""
        fenced = '```json\n{"action":"home","color":null,"colors":null,"target":null,"reason":"k"}\n```'
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(vla.subprocess, "run", _mock_run_returning(fenced)):
            result = vla._call_claude_cli("go home")
        self.assertEqual(result["action"], "home")

    def test_strips_plain_fence(self) -> None:
        """A ``` without `json` should also work (some Claude variants)."""
        fenced = '```\n{"action":"stack","color":null,"colors":["red","green"],"target":null,"reason":"k"}\n```'
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(vla.subprocess, "run", _mock_run_returning(fenced)):
            result = vla._call_claude_cli("stack red and green")
        self.assertEqual(result["action"], "stack")
        self.assertEqual(result["colors"], ["red", "green"])

    def test_extracts_json_from_chatty_output(self) -> None:
        """If Claude prepends explanation text before the JSON, regex still
        grabs the first {...} object."""
        chatty = (
            "Sure, here's the parsed action:\n"
            '{"action":"pick","color":"green","colors":null,"target":null,"reason":"k"}\n'
            "Hope that helps!"
        )
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(vla.subprocess, "run", _mock_run_returning(chatty)):
            result = vla._call_claude_cli("grab green")
        self.assertEqual(result["action"], "pick")
        self.assertEqual(result["color"], "green")


# ============================================================================
# Failure modes — every one must return None (NOT raise)
# ============================================================================


class FailureModesTest(unittest.TestCase):
    def test_timeout_returns_none(self) -> None:
        """A hung Claude subprocess must not block the demo thread."""
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(
                vla.subprocess, "run",
                side_effect=subprocess.TimeoutExpired(cmd=["claude"], timeout=2.5),
        ):
            self.assertIsNone(vla._call_claude_cli("pick red", timeout=2.5))

    def test_empty_stdout_returns_none(self) -> None:
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(vla.subprocess, "run", _mock_run_returning("")):
            self.assertIsNone(vla._call_claude_cli("pick red"))

    def test_no_json_in_stdout_returns_none(self) -> None:
        """Pure prose with no `{...}` — regex misses → return None."""
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(vla.subprocess, "run",
                                _mock_run_returning("I don't understand your command.")):
            self.assertIsNone(vla._call_claude_cli("hgjdkl"))

    def test_malformed_json_returns_none(self) -> None:
        """`{...}` matches but the body isn't parseable JSON."""
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(vla.subprocess, "run",
                                _mock_run_returning('{action: pick, color: red}')):  # no quotes
            self.assertIsNone(vla._call_claude_cli("pick red"))

    def test_nonzero_returncode_with_no_json_returns_none(self) -> None:
        """`check=False` means we don't raise on non-zero exit, we just look
        at stdout. If the CLI failed and stdout is empty, return None."""
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(vla.subprocess, "run",
                                _mock_run_returning("", returncode=1)):
            self.assertIsNone(vla._call_claude_cli("pick red"))

    def test_nonzero_returncode_with_valid_json_still_parses(self) -> None:
        """Edge case: CLI exits non-zero but printed valid JSON anyway. We
        currently trust stdout. Locking this in so a future refactor that
        adds a `if returncode != 0: return None` is an explicit decision."""
        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(
                vla.subprocess, "run",
                _mock_run_returning(
                    '{"action":"pick","color":"red","colors":null,"target":null,"reason":"k"}',
                    returncode=2,
                ),
        ):
            result = vla._call_claude_cli("pick red")
        # Document behavior — currently truthy. If you change this, update the
        # test.
        self.assertIsNotNone(result)
        self.assertEqual(result["action"], "pick")


# ============================================================================
# Prompt construction — context plumbing
# ============================================================================


class PromptContextTest(unittest.TestCase):
    """Verify that `history` and `world_state` actually flow into the prompt
    so Claude can resolve "do it again" / "the leftmost block" references.
    We assert by inspecting the `input=` argument passed to subprocess.run."""

    def _capture_prompt(self, **call_kwargs) -> str:
        captured = {}

        def fake_run(*args, **kwargs):
            captured["input"] = kwargs.get("input", "")
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        with mock.patch.object(vla.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(vla.subprocess, "run", side_effect=fake_run):
            vla._call_claude_cli("pick red", **call_kwargs)
        return captured["input"]

    def test_user_input_included(self) -> None:
        prompt = self._capture_prompt()
        self.assertIn("pick red", prompt)

    def test_history_injected(self) -> None:
        prompt = self._capture_prompt(
            history=[("pick blue", {"action": "pick", "color": "blue",
                                     "colors": None, "target": None})],
        )
        self.assertIn("pick blue", prompt)
        self.assertIn("Recent commands", prompt)

    def test_world_state_injected(self) -> None:
        prompt = self._capture_prompt(
            world_state={
                "base_x": 0.5,
                "held_color": "red",
                "blocks": [("red", 0.9, 0.1), ("green", 1.1, 0.1)],
            },
        )
        self.assertIn("Current scene", prompt)
        self.assertIn("holding the red block", prompt)
        self.assertIn("red", prompt)
        self.assertIn("green", prompt)

    def test_no_history_omits_recent_commands_section(self) -> None:
        """When history is None the prompt must NOT include the Recent
        commands header (no empty-list rendering)."""
        prompt = self._capture_prompt()
        self.assertNotIn("Recent commands", prompt)

    def test_no_world_state_omits_current_scene_section(self) -> None:
        """When world_state is None the prompt must NOT include Current
        scene — keeps the prompt short for offline-ish calls."""
        prompt = self._capture_prompt()
        self.assertNotIn("Current scene", prompt)


if __name__ == "__main__":
    unittest.main()
