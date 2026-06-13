"""Arm B's physics lecture — the offset-tower stability experiment.

Each round, the fixed right arm stacks its three grey workpieces into a
tower whose layers step sideways by a per-round offset. With equal-mass
cubes of half-width ``BLOCK_HALF`` and cumulative per-layer offset ``d``,
the combined center of mass of the top two layers sits ``1.5 d`` from the
bottom block's center — the tower genuinely topples (real XPBD dynamics,
not animation) once that excursion passes the support half-width:
``d > BLOCK_HALF / 1.5 ≈ 6.7 cm``. The schedule below brackets that
threshold so the audience sees stable → stable → collapse.

The coordinator drives only Arm B's TaskExecutor (the audience keeps
Arm A), sequencing pick/place programs one at a time; the executor's
per-frame ``update`` — pumped by the main loop — performs the motion.
Requires ``--real-blocks``: teleported blocks place exactly and can
never topple, so there would be no physics to show.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from .physics import BLOCK_HALF, World
from .tasks import TaskExecutor

# Tower column sits mid-band for Arm B (anchor x=2.40, proven reach
# 1.50..2.50). Layers step toward -x, so a collapse spills LEFT into the
# empty stretch of the band instead of off its right edge.
COLUMN_X = 2.05
# Per-layer offset per round (m). Theory: topple at d > BLOCK_HALF/1.5.
OFFSET_SCHEDULE = (0.0, 0.04, 0.09)
SETTLE_S = 2.0       # let the finished tower ring down before the verdict
VERDICT_HOLD_S = 3.0  # leave the outcome (and banner) on stage
TOPPLE_ANGLE_RAD = 0.30   # ~17° — settled stable towers stay well under this


class StabilityExperiment:
    """Build → observe → verdict → cleanup → loop, forever.

    Call :meth:`update` once per frame, then pump the executor as usual.
    Emits human-readable beats through ``on_event`` (status line + banner
    text) so the main loop owns all presentation.
    """

    def __init__(
        self,
        world: World,
        exe_b: TaskExecutor,
        *,
        colors: tuple[str, ...] = ("workpiece", "slate", "zinc"),
        column_x: float = COLUMN_X,
        offsets: tuple[float, ...] = OFFSET_SCHEDULE,
        on_event: Callable[[str, str], None] | None = None,
    ) -> None:
        self.world = world
        self.exe = exe_b
        self.colors = [c for c in colors if world.find_block(c) is not None]
        self.column_x = column_x
        self.offsets = offsets
        self.on_event = on_event or (lambda kind, text: None)
        self._home: dict[str, tuple[float, float]] = {
            c: world.find_block(c).xz for c in self.colors
        }
        self.round_idx = 0
        self.toppled_last_round = False
        self._begin_build()

    # -- phase setup ----------------------------------------------------

    def _begin_build(self) -> None:
        self._phase = "build"
        self._layer = 0           # next layer to stack
        self._active = False      # a pick+place program is in flight
        self._wait_until: float | None = None
        d = self.offsets[self.round_idx]
        self.on_event(
            "round",
            f"Round {self.round_idx + 1}: offset {d * 100:.0f} cm/layer "
            f"(theory: topple >{BLOCK_HALF / 1.5 * 100:.0f})",
        )

    def _begin_cleanup(self) -> None:
        self._phase = "cleanup"
        self._layer = 0
        self._active = False
        self._wait_until = None

    # -- queries --------------------------------------------------------

    @property
    def phase(self) -> str:
        return self._phase

    def _layer_target(self, i: int) -> tuple[float, float]:
        """Center of layer i: stepped -x by the round's offset, ascending z."""
        d = self.offsets[self.round_idx]
        return (self.column_x - i * d, (2 * i + 1) * BLOCK_HALF)

    def _stacked_blocks(self) -> list:
        return [self.world.find_block(c) for c in self.colors[: self._layer]]

    def toppled(self) -> bool:
        """Real-physics verdict: a block tipped past TOPPLE_ANGLE_RAD, or the
        top layer is no longer near its stacked height."""
        blocks = self._stacked_blocks()
        if not blocks:
            return False
        if any(abs(getattr(b, "angle", 0.0)) > TOPPLE_ANGLE_RAD for b in blocks):
            return True
        if self._layer >= len(self.colors):
            top = blocks[-1]
            expected_z = (2 * (len(self.colors) - 1) + 1) * BLOCK_HALF
            if top.xz[1] < expected_z - BLOCK_HALF:
                return True
        return False

    def com_overlay(self) -> tuple[float, float, float, bool] | None:
        """(com_x, base_min_x, base_max_x, stable) for the layers placed so
        far, from the blocks' REAL poses — None when nothing is stacked or
        during cleanup.

        ``com_x`` is the combined CoM of every layer resting ON the bottom
        block (i.e. the load it must support), and ``stable`` is the textbook
        tipping criterion: that CoM projects inside the bottom block's
        support span. For the 3-block lecture the load is the top two layers,
        whose CoM sits 1.5*offset off the base — so the overlay flips amber at
        offset > BLOCK_HALF / 1.5 (~6.7 cm), exactly where XPBD topples it.
        (Using the all-layers mean instead would only flip at offset > r and
        would stay green through the whole scheduled collapse.)"""
        if self._phase == "cleanup" or self._layer == 0:
            return None
        blocks = self._stacked_blocks()
        base = blocks[0].xz[0]
        load = blocks[1:] or blocks  # layers resting on the bottom block
        com_x = sum(b.xz[0] for b in load) / len(load)
        return (com_x, base - BLOCK_HALF, base + BLOCK_HALF, abs(com_x - base) <= BLOCK_HALF)

    # -- per-frame ------------------------------------------------------

    def update(self) -> None:
        if self._phase == "build":
            self._update_build()
        elif self._phase == "observe":
            self._update_observe()
        elif self._phase == "verdict":
            if time.perf_counter() >= self._wait_until:
                self._begin_cleanup()
        elif self._phase == "cleanup":
            self._update_cleanup()

    def _update_build(self) -> None:
        if self._active:
            if not self.exe.busy:
                self._active = False
                self._layer += 1
            return
        if self._layer >= len(self.colors):
            self._phase = "observe"
            self._wait_until = time.perf_counter() + SETTLE_S
            return
        if not self.exe.busy:
            color = self.colors[self._layer]
            target = self._layer_target(self._layer)
            self.exe.queue(self.exe.make_pick(color) + self.exe.make_place(target))
            self._active = True

    def _update_observe(self) -> None:
        if time.perf_counter() < self._wait_until:
            return
        self.toppled_last_round = self.toppled()
        d = self.offsets[self.round_idx]
        if self.toppled_last_round:
            self.on_event(
                "topple",
                f"TOPPLED — {d * 100:.0f} cm/layer pushed the CoM past the base",
            )
        else:
            self.on_event("stable", f"Stable at {d * 100:.0f} cm/layer")
        self._wait_until = time.perf_counter() + VERDICT_HOLD_S
        self._phase = "verdict"

    def _update_cleanup(self) -> None:
        if self._active:
            if not self.exe.busy:
                self._active = False
                self._layer += 1
            return
        if self._layer >= len(self.colors):
            # Round over: a survivor graduates to a bigger offset, a collapse
            # restarts the lecture from the aligned tower.
            self.round_idx = 0 if self.toppled_last_round else min(
                self.round_idx + 1, len(self.offsets) - 1
            )
            self._begin_build()
            return
        if not self.exe.busy:
            color = self.colors[self._layer]
            self.exe.queue(
                self.exe.make_pick(color) + self.exe.make_place(self._home[color])
            )
            self._active = True

