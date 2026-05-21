"""Unit tests for `demo_live.pipeline.build_plan_from`.

`build_plan_from` is the single source of truth that maps a parsed VLA
action (pick / place / stack / drive / wave / point / bow / dance / home /
unknown) onto an arm waypoint program. Both the keyword preflight in
`__main__.py` and the rehearsal `arm_b:` dispatch call it, so a regression
here can silently break a live demo. The 14 tests below lock in every
action branch + the most common edge cases.

A FakeWorld + stub controller keeps the tests fast (no Warp boot, ~1 ms
total) and deterministic — same pattern as test_tasks.py.
"""

from __future__ import annotations

import unittest

from demo_live import pipeline, tasks
from demo_live.physics import Block


class FakeWorld:
    """Just enough of physics.World for tasks.TaskExecutor + pipeline."""

    base_drive_speed = 0.8

    def __init__(self) -> None:
        self.base_x = 0.0
        self.base_target_x = 0.0
        self._blocks = {
            "red": Block(color="red", xz=(0.9, 0.1)),
            "green": Block(color="green", xz=(1.1, 0.1)),
            "blue": Block(color="blue", xz=(1.3, 0.1)),
            "yellow": Block(color="yellow", xz=(-0.9, 0.1)),
        }
        self.drive_calls: list[float] = []

    def find_block(self, color: str) -> Block | None:
        return self._blocks.get(color)

    def move_block(self, block: Block, xz: tuple[float, float]) -> None:
        pass

    def drive_to(self, target_x: float) -> None:
        self.drive_calls.append(target_x)
        self.base_target_x = target_x


class StubController:
    """Just .go_home() — `build_plan_from` only touches the controller
    inside the "home" branch."""

    def __init__(self) -> None:
        self.home_calls = 0

    def go_home(self) -> None:
        self.home_calls += 1


def _build_plan_kwargs(world: FakeWorld | None = None,
                       controller: StubController | None = None,
                       **kw) -> tuple[list[tasks.Waypoint], FakeWorld, StubController]:
    """Helper: build (plan, world, controller) for a given action call."""
    w = world or FakeWorld()
    c = controller or StubController()
    ex = tasks.TaskExecutor(world=w, ctrl=object())
    kw.setdefault("action", "unknown")
    kw.setdefault("color", None)
    kw.setdefault("colors", None)
    kw.setdefault("target", None)
    plan = pipeline.build_plan_from(ex, c, w, **kw)
    return plan, w, c


# ============================================================================
# Functional actions: pick / place / stack / drive
# ============================================================================


class PickActionTest(unittest.TestCase):
    def test_pick_red_returns_non_empty(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="pick", color="red")
        self.assertGreater(len(plan), 0)

    def test_pick_without_color_returns_empty(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="pick", color=None)
        self.assertEqual(plan, [])

    def test_pick_unknown_color_returns_empty(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="pick", color="purple")
        self.assertEqual(plan, [])


class PlaceActionTest(unittest.TestCase):
    def test_place_with_target_returns_non_empty(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="place", target=[-0.6, 0.0])
        self.assertGreater(len(plan), 0)

    def test_place_without_target_returns_empty(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="place", target=None)
        self.assertEqual(plan, [])

    def test_place_with_target_as_tuple_works(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="place", target=(-0.6, 0.0))
        self.assertGreater(len(plan), 0)


class StackActionTest(unittest.TestCase):
    def test_stack_with_colors(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="stack",
                                          colors=["red", "green", "blue"])
        self.assertGreater(len(plan), 5)   # at least one pick+place per block

    def test_stack_without_colors_defaults_to_rgb(self) -> None:
        """Empty colors should still produce a stack (default red/green/blue)."""
        plan, _, _ = _build_plan_kwargs(action="stack", colors=None)
        self.assertGreater(len(plan), 5)


class DriveActionTest(unittest.TestCase):
    def test_drive_with_target_returns_non_empty(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="drive", target=[0.7, 0.0])
        self.assertGreater(len(plan), 0)

    def test_drive_clamps_extreme_targets(self) -> None:
        """build_plan_from should clamp drive target into the [-1.6, 1.6]
        workspace range — verified by the resulting `make_drive` label."""
        plan, _, _ = _build_plan_kwargs(action="drive", target=[99.0, 0.0])
        # The clamped value shows up in the first waypoint's label.
        self.assertIn("+1.60", plan[0].label, plan[0].label)


class HomeActionTest(unittest.TestCase):
    def test_home_triggers_controller_and_drive(self) -> None:
        plan, world, controller = _build_plan_kwargs(action="home")
        self.assertEqual(plan, [])
        self.assertEqual(controller.home_calls, 1)
        self.assertEqual(world.drive_calls, [0.0])


# ============================================================================
# Decorative gestures: wave / point / bow / dance
# These were missed by the original action-whitelist (preflight regression);
# the tests below would have caught that bug immediately.
# ============================================================================


class GestureActionsTest(unittest.TestCase):
    def test_wave_returns_non_empty(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="wave")
        self.assertGreater(len(plan), 0)

    def test_point_default_left(self) -> None:
        """No `colors` parameter should default the direction to 'left'."""
        plan, _, _ = _build_plan_kwargs(action="point")
        self.assertGreater(len(plan), 0)
        self.assertLess(plan[0].target_xz[0], 0.7)   # left of home (0.7)

    def test_point_right(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="point", colors=["right"])
        self.assertGreater(plan[0].target_xz[0], 0.7)

    def test_point_audience(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="point", colors=["audience"])
        # Audience target is up-and-slightly-left.
        self.assertGreater(plan[0].target_xz[1], 1.0)

    def test_point_unknown_direction_falls_back_to_left(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="point", colors=["sideways"])
        self.assertLess(plan[0].target_xz[0], 0.7)

    def test_bow_returns_non_empty(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="bow")
        self.assertGreater(len(plan), 0)
        # Bow dips below home Z (1.0).
        self.assertLess(plan[0].target_xz[1], 1.0)

    def test_dance_returns_non_empty(self) -> None:
        plan, _, _ = _build_plan_kwargs(action="dance")
        self.assertGreaterEqual(len(plan), 3)


# ============================================================================
# Unknown / no-op
# ============================================================================


class UnknownActionTest(unittest.TestCase):
    def test_unknown_returns_empty_plan(self) -> None:
        plan, world, controller = _build_plan_kwargs(action="unknown")
        self.assertEqual(plan, [])
        self.assertEqual(controller.home_calls, 0)
        self.assertEqual(world.drive_calls, [])

    def test_garbage_action_returns_empty_plan(self) -> None:
        """An action enum we don't know about (e.g. typo in Claude's
        response) shouldn't crash — it should just produce no plan."""
        plan, _, _ = _build_plan_kwargs(action="dance_off")
        self.assertEqual(plan, [])


if __name__ == "__main__":
    unittest.main()
