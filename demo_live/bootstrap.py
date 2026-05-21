"""Startup helpers extracted from `__main__.py`: pre-warming Warp kernels +
Python fast paths so the first audience interaction is instant, plus
constructing the optional secondary "Arm B" rig.

`init_pygame` and the primary `World/Controller/Catcher/TaskExecutor`
constructors remain inline in `__main__.main()` because they're tightly
coupled to the argparse Namespace.
"""

from __future__ import annotations

from .catcher import BallCatcher
from .control import FKJointController, JointController
from .physics import FKArmRig, World
from .tasks import TaskExecutor

# Type alias for the tuple `make_arm_b` returns. `None`-fillers when the
# industrial dual-arm scene is disabled keep the call site's destructuring
# stable: `rig, ctrl, exe, grip = make_arm_b(...)` works in both modes.
ArmBBundle = tuple[
    FKArmRig | None,
    FKJointController | None,
    TaskExecutor | None,
    dict | None,
]


def make_arm_b(
    world: World,
    *,
    industrial: bool,
    anchor_world_x: float,
) -> ArmBBundle:
    """Construct the optional secondary arm (FK-only, no Newton physics).

    Returns `(rig, controller, executor, gripper_state)`. When `industrial`
    is False, all four are `None` so the caller's tuple-destructuring stays
    stable across modes — `arm_b_*` references downstream just check for
    `executor_b is not None` before touching the rig.

    `world` is the live, possibly-just-reset Newton world. The secondary
    arm shares `world.blocks` so picks/places interact with Arm A.
    """
    if not industrial:
        return None, None, None, None
    rig = FKArmRig(anchor_world_x=anchor_world_x)
    controller_fk = FKJointController(rig)
    executor_fk = TaskExecutor(
        world,
        controller_fk,
        label="B",
        anchor_world_x=lambda: rig.anchor_world_x,
        arm_state_provider=rig.arm_state_from_target,
    )
    gripper_state: dict = {"open": 1.0, "hand_angle": 0.0}
    return rig, controller_fk, executor_fk, gripper_state


def prewarm(
    world: World,
    controller: JointController,
    catcher: BallCatcher,
    executor: TaskExecutor,
) -> None:
    """Silently run one of each major operation so Warp JIT compiles its
    kernels and Python fast-paths are hot before any audience interaction.

    The first cold boot compiles ~10 kernels (~10 s on cold cache, ~50 ms
    on warm cache). Prewarming up front means the first live `1`/`2`/`3`
    keystroke feels instant.
    """
    # Physics + arm PD.
    for _ in range(15):
        controller.update(1 / 60)
        world.step()
    # Ball integration + catcher.
    world.launch_ball((1.5, 0.7), (-1.8, 3.4))
    for _ in range(60):
        world.integrate_ball(1 / 60)
        world.step()
    world.park_ball()
    # Task executor (queue + immediate clear, forces IK + ease path warmup).
    first_pick = executor.make_pick("red")
    executor.queue([first_pick[0]] if first_pick else [])
    for _ in range(30):
        executor.update(1 / 60)
        controller.update(1 / 60)
        world.step()
    executor.clear()
    controller.go_home()
    for _ in range(30):
        controller.update(1 / 60)
        world.step()
