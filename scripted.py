"""Static rehearsal scripts and scenario constants used by `--scripted`
and the `F5` quick-rehearsal hotkey.

Only the *data* lives here. The step engine that interprets each
`catch:start` / `type:` / `voice:` / `arm_b:` / `reset` token stays in
`__main__.py` because it mutates the heavily-closured loop state
(`mode_label`, `status`, `world`, `controller`, `executor`, ...).
Extracting the engine cleanly would require a full AppState refactor,
which is deferred.
"""

from __future__ import annotations

from dataclasses import dataclass

# Each tuple: (wait_after_this_step_seconds, step_to_run_now). The leading
# delay is honored by the step engine via `time.perf_counter() >=
# rehearsal_next_at`.
RehearsalStep = tuple[float, str]

# Beats 1–4 of the classroom rehearsal. Industrial mode appends an Arm B
# parallel pick before the final reset (see `industrial_arm_b_insert`).
REHEARSAL_SCRIPT_DEFAULT: list[RehearsalStep] = [
    # Beat 1 — classical control, no AI. Arm A catches balls.
    (12.0, "catch:start"),
    (0.3, "catch:stop"),
    (1.5, "wait"),
    # Beat 2 — TYPED input. With hybrid preflight the arm starts moving the
    # moment typing finishes (~1s); Claude streams a confirmation in the
    # background a few seconds later.
    (10.0, "type:pick up the red block"),     # type 1s + arm 7s + buffer
    (6.0, "type:drive right"),                # type 0.5s + drive 4s + buffer
    # Beat 3 — VOICE input.
    (10.0, "voice:peter ride|pick red"),      # listen 1.5+0.7 + arm 6s + buffer
    # Beat 4 — single-arm classroom flow by default. Industrial mode
    # appends the Arm B parallel pick below.
    (1.0, "type:put the red block on the left"),
    (1.5, "reset"),
]

# Step appended (just before the final reset) when --industrial enables the
# secondary Arm B. Runs in parallel with the in-flight Arm A LLM parse,
# using only the deterministic keyword fallback so the two arms never
# contend for the Claude subprocess.
INDUSTRIAL_ARM_B_INSERT: RehearsalStep = (16.0, "arm_b:pick blue")

# F5 hotkey: pre-stage "everything is warm" rehearsal. Forces VLA into
# keyword-only mode (via _call_claude_cli stub) so it's deterministic.
REHEARSAL_SCRIPT_F5: list[RehearsalStep] = [
    (10.0, "catch:start"),
    (0.3, "catch:stop"),
    (6.0, "vla:pick up the red block"),
    (3.0, "vla:drive right"),
    (6.0, "vla:put the red block on the left"),
    (3.0, "vla:drive home"),
    (22.0, "vla:build a tower from red green and blue"),
    (1.0, "reset"),
]


def build_default_rehearsal(*, industrial: bool) -> list[RehearsalStep]:
    """Return a fresh copy of the default rehearsal script, with the Arm B
    step spliced in for --industrial. The copy isolates the caller from
    accidental mutations of the module-level constant."""
    script = list(REHEARSAL_SCRIPT_DEFAULT)
    if industrial:
        script.insert(-1, INDUSTRIAL_ARM_B_INSERT)
    return script


# ----------------------------------------------------------------- Arm B idle
#
# When industrial mode is on but no rehearsal is running, the secondary
# Arm B perpetually shuttles its dedicated "workpiece" block back and
# forth between two positions in its reachable zone (anchor x=2.40, so
# both 1.50 and 2.50 sit comfortably ~0.10–0.90 m from the shoulder).
# Reads as "the right arm is doing real factory work" while Arm A handles
# the audience — far more meaningful than idle gestures.
#
# Each step is `action="place"` with color="workpiece" + a target. The
# `pipeline.build_plan_from` "place with color when not holding" branch
# emits a full pick-then-place program automatically, so the workpiece
# follows the gripper through every cycle. No separate dispatcher needed.


@dataclass(frozen=True)
class ArmBIdleStep:
    """One entry in `ARM_B_IDLE_CYCLE` — directly consumed by
    `pipeline.build_plan_from(executor_b, controller_b, world,
    step.action, step.color, step.colors, step.target)`."""

    action: str
    color: str | None = None
    colors: list[str] | None = None
    target: tuple[float, float] | None = None


# Ping-pong shuttle: workpiece goes 1.50 ↔ 2.50 forever. The initial
# spawn at x=2.00 (see physics.py block_layout) means the first cycle
# step picks from 2.00, drops at 2.50; the next picks from 2.50, drops
# at 1.50; thereafter the workpiece oscillates between the two endpoints.
ARM_B_IDLE_CYCLE: list[ArmBIdleStep] = [
    ArmBIdleStep(action="place", color="workpiece", target=(2.50, 0.0)),
    ArmBIdleStep(action="place", color="workpiece", target=(1.50, 0.0)),
]

# Pause after each shuttle completes before queueing the next. Long
# enough that the audience sees the workpiece "land" cleanly, short
# enough that the right arm stays visibly busy.
ARM_B_IDLE_PAUSE_S = 1.0
