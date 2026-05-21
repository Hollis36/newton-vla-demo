"""Pure pipeline helpers extracted from `__main__.py`:

  - `world_snapshot(world, executor)`  : the dict the VLA layer feeds to
    Claude as scene context.
  - `build_plan_from(executor, controller, world, action, color, colors,
    target)`: translate one parsed VLA action into an arm waypoint program.

Both functions are pure-ish (no module-level state); they used to be inner
functions of `main()` with closures over `world`, `executor`, `controller`.
Lifting them to module-level lets unit tests exercise the plan-building
logic in isolation and makes the surrounding code shorter.
"""

from __future__ import annotations

from typing import Any

from .control import JointController
from .physics import World
from .tasks import TaskExecutor, Waypoint


def world_snapshot(world: World, executor: TaskExecutor) -> dict[str, Any]:
    """Snapshot of the live scene that the VLA layer feeds Claude as
    `world_state`. Lets the LLM resolve references like "the leftmost
    block" or "drop it where you picked it up from".
    """
    held_obj = executor.held
    held_color = getattr(held_obj, "color", None) if held_obj is not None else None
    return {
        "base_x": float(world.base_x),
        "held_color": held_color,
        "blocks": [(b.color, float(b.xz[0]), float(b.xz[1])) for b in world.blocks],
    }


def build_plan_from(
    executor: TaskExecutor,
    controller: JointController,
    world: World,
    action: str | None,
    color: str | None,
    colors: list[str] | None,
    target: tuple[float, float] | list[float] | None,
) -> list[Waypoint]:
    """Translate one parsed (action, color, colors, target) tuple into an
    arm program for the given executor.

    Returns the plan list (possibly empty); for action="home" it triggers
    controller side effects directly and returns []. Mirrors the original
    `_build_plan_from` inner function — the hybrid pipeline calls this
    twice per command (preflight + Claude refinement)."""
    plan: list[Waypoint] = []
    if action == "pick" and color:
        plan = executor.make_pick(color)
    elif action == "place" and target is not None:
        target_xz = (float(target[0]), float(target[1]))
        if color and executor.held is None:
            plan = executor.make_pick(color) + executor.make_place(target_xz)
        else:
            plan = executor.make_place(target_xz)
    elif action == "stack":
        cs = colors or ["red", "green", "blue"]
        plan = executor.make_stack(cs)
    elif action == "drive" and target is not None:
        target_x = max(-1.6, min(1.6, float(target[0])))
        plan = executor.make_drive(target_x)
    elif action == "wave":
        plan = executor.make_wave()
    elif action == "point":
        direction = "left"
        if colors:
            cand = str(colors[0]).lower()
            if cand in ("left", "right", "audience"):
                direction = cand
        plan = executor.make_point(direction=direction)
    elif action == "bow":
        plan = executor.make_bow()
    elif action == "dance":
        plan = executor.make_dance()
    elif action == "home":
        controller.go_home()
        world.drive_to(0.0)
    return plan
