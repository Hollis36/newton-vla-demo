"""End-to-end regression tests for the scripted demo flows.

These tests spawn `python -m demo_live --scripted X --bench N --state-dump PATH`
as a subprocess under SDL_VIDEODRIVER=dummy, then read the terminal World
state from the dumped JSON and assert that the scenario actually accomplished
its goal (block lifted, tower stacked, ball caught) rather than only that
frames rendered at 60 fps.

They are slow (~60 s wall-clock total) but invaluable as a safety net for
the upcoming refactor of __main__.py and scene.py.

Run them in isolation with:

    uv run --extra demo python -m unittest \\
        demo_live.tests.test_scripted_flows -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_scripted(
    scenario: str,
    duration: float,
    extra_args: list[str] | None = None,
) -> dict:
    """Spawn the demo, run a scripted scenario, return the terminal-state dict.

    Uses the current Python interpreter (sys.executable) so the active
    virtualenv is honored — `make test` already invokes us under `uv run`,
    so no nested uv is needed.
    """
    extra = list(extra_args or [])
    with tempfile.NamedTemporaryFile(
        prefix=f"demo_state_{scenario}_", suffix=".json", delete=False
    ) as fp:
        dump_path = Path(fp.name)
    try:
        env = os.environ.copy()
        env["SDL_VIDEODRIVER"] = "dummy"
        cmd = [
            sys.executable,
            "-m",
            "demo_live",
            "--scripted",
            scenario,
            "--bench",
            str(duration),
            "--state-dump",
            str(dump_path),
            *extra,
        ]
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=duration + 60,
        )
        if result.returncode != 0 or not dump_path.exists():
            raise RuntimeError(
                f"scripted {scenario} failed (rc={result.returncode}):\n"
                f"stdout:\n{result.stdout[-2000:]}\n"
                f"stderr:\n{result.stderr[-2000:]}"
            )
        return json.loads(dump_path.read_text())
    finally:
        dump_path.unlink(missing_ok=True)


def _block_by_color(state: dict, color: str) -> dict:
    for b in state["blocks"]:
        if b["color"] == color:
            return b
    raise AssertionError(f"no block with color={color!r} in dump")


class ScriptedCatchTest(unittest.TestCase):
    """`--scripted catch` should auto-launch balls and catch most of them.

    Catcher behavior under XPBD jitter is mildly stochastic, so we assert
    on a STATISTICAL outcome over a longer window (12 s = ~7-8 attempts)
    rather than a per-throw guarantee. The two-stage check first verifies
    the launcher fired, then the catcher caught — that way a regression
    that breaks ball physics surfaces differently from one that breaks IK.
    """

    def test_auto_launcher_fires(self) -> None:
        state = _run_scripted("catch", duration=12.0)
        self.assertGreaterEqual(
            state["catcher"]["attempt_count"], 3,
            "auto-launcher should have thrown >=3 balls in 12 s; "
            f"got {state['catcher']}",
        )

    def test_catches_majority_of_throws(self) -> None:
        state = _run_scripted("catch", duration=12.0)
        c = state["catcher"]
        self.assertGreaterEqual(c["attempt_count"], 3)
        # Catch rate is normally 70-90% in nominal conditions; if it drops
        # below 50% something has regressed (IK, intercept tolerance, etc.).
        self.assertGreaterEqual(
            c["catch_count"], max(1, c["attempt_count"] // 2),
            f"catch rate too low: {c['catch_count']}/{c['attempt_count']}",
        )


class ScriptedPickTest(unittest.TestCase):
    """`--scripted pick` does make_pick('red') + make_place((-0.6, 0)).

    By bench end the red block should have moved from its initial x ≈ +0.9
    to near x = -0.6, and the arm should no longer be holding anything.
    """

    def test_red_block_moved_to_left(self) -> None:
        state = _run_scripted("pick", duration=6.0)
        red = _block_by_color(state, "red")
        self.assertAlmostEqual(
            red["x"], -0.6, delta=0.15,
            msg=f"red block should be placed near x=-0.6; got {red}",
        )
        self.assertIsNone(
            state["held_color"],
            f"executor should have released the block; got held={state['held_color']!r}",
        )

    def test_other_blocks_untouched(self) -> None:
        state = _run_scripted("pick", duration=6.0)
        green = _block_by_color(state, "green")
        blue = _block_by_color(state, "blue")
        # Green starts near x=1.1, blue near x=1.5 — neither should move.
        self.assertAlmostEqual(green["x"], 1.1, delta=0.05)
        self.assertAlmostEqual(blue["x"], 1.5, delta=0.05)


class ScriptedStackTest(unittest.TestCase):
    """`--scripted stack` should build a tower at x ≈ STACK_X = -0.40."""

    def test_three_blocks_stacked(self) -> None:
        state = _run_scripted("stack", duration=20.0)
        # All three building blocks should have migrated to STACK_X (~-0.40)
        # with z increasing as they pile up.
        colors = ("red", "green", "blue")
        positions = [_block_by_color(state, c) for c in colors]
        for c, b in zip(colors, positions, strict=True):
            self.assertAlmostEqual(
                b["x"], -0.40, delta=0.12,
                msg=f"{c} block should be at STACK_X (-0.40); got {b}",
            )
        zs = [b["z"] for b in positions]
        self.assertLess(zs[0], zs[1], "green should be above red")
        self.assertLess(zs[1], zs[2], "blue should be above green")


class ScriptedVlaTest(unittest.TestCase):
    """`--scripted vla --vla-command "stack a tower"` exercises the same
    end-to-end VLA → TaskExecutor path that audience commands take.

    The keyword fallback inside vla.py handles "stack a tower" deterministically
    even if `claude --print` is unavailable, so this test is reliable on CI.
    """

    def test_vla_stack_a_tower(self) -> None:
        state = _run_scripted(
            "vla", duration=20.0,
            extra_args=["--vla-command", "stack a tower"],
        )
        positions = [_block_by_color(state, c) for c in ("red", "green", "blue")]
        for c, b in zip(("red", "green", "blue"), positions, strict=True):
            self.assertAlmostEqual(
                b["x"], -0.40, delta=0.15,
                msg=f"{c} should be on the tower at x≈-0.40; got {b}",
            )
        zs = [b["z"] for b in positions]
        self.assertLess(zs[0], zs[1])
        self.assertLess(zs[1], zs[2])


if __name__ == "__main__":
    unittest.main()
