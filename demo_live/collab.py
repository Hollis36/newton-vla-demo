"""Two-arm collaborative tower build — the right arm's purposeful behavior.

Arm A (mobile) fetches teaching blocks from the field and sets them on a
handoff slot; Arm B (fixed) picks from the slot and stacks them into a tower in
its own reach zone. When the tower is complete the roles reverse to tear it
down, then it loops — so the dual-arm workstation continuously shows the two
arms cooperating instead of one arm mindlessly shuttling a single block.

The coordinator only sequences high-level pick/place programs onto the two
existing TaskExecutors, gated on a single-slot handoff; the executors' own
per-frame `update` — pumped by the main loop — performs the motion. Works in
both teleport and ``--real-blocks`` modes: Arm B's executor already drives the
same grab_block/release_block grasp path as Arm A.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .physics import BLOCK_HALF, World
from .tasks import TaskExecutor

# Both the handoff slot and the tower column must sit inside Arm B's reach band
# (it is fixed at x=2.40; the legacy workpiece shuttle proves 1.50..2.50) and
# clear of the grey workpiece parked at x=2.0.
HANDOFF_X = 1.50
TOWER_X = 1.70
HOLD_S = 2.5     # admire the finished tower before tearing it down


@dataclass
class _Transfer:
    """Move one colored block from wherever it currently is, via the handoff
    slot, to ``dest``: ``deliver`` brings it to the handoff, ``take`` carries it
    onward and places it."""

    color: str
    deliver: TaskExecutor
    take: TaskExecutor
    dest: tuple[float, float]


class CollaborativeBuild:
    """Pipelined relay tower build across Arm A (mobile) and Arm B (fixed).

    Call :meth:`update` once per frame, after which the two executors must be
    pumped as usual by the caller. The cycle is build → admire → teardown →
    loop, forever.
    """

    def __init__(
        self,
        world: World,
        exe_a: TaskExecutor,
        exe_b: TaskExecutor,
        *,
        colors: tuple[str, ...] = ("red", "green", "blue"),
        handoff_x: float = HANDOFF_X,
        tower_x: float = TOWER_X,
    ) -> None:
        self.world = world
        self.exe_a = exe_a
        self.exe_b = exe_b
        # Only build with blocks that actually exist in this world.
        self.colors = [c for c in colors if world.find_block(c) is not None]
        self.handoff = (handoff_x, BLOCK_HALF)
        self.tower_x = tower_x
        # Where each block started, so teardown can return it home.
        self._home: dict[str, tuple[float, float]] = {
            c: world.find_block(c).xz for c in self.colors
        }
        self._begin_build()

    # -- phase setup ----------------------------------------------------

    def _begin_build(self) -> None:
        self._phase = "build"
        self._transfers = [
            _Transfer(c, self.exe_a, self.exe_b, (self.tower_x, (2 * i + 1) * BLOCK_HALF))
            for i, c in enumerate(self.colors)
        ]
        self._reset_pointers()

    def _begin_teardown(self) -> None:
        self._phase = "teardown"
        # Top block first so we never pull a block out from under another.
        self._transfers = [
            _Transfer(c, self.exe_b, self.exe_a, self._home[c])
            for c in reversed(self.colors)
        ]
        self._reset_pointers()

    def _reset_pointers(self) -> None:
        self._deliver_idx = 0      # next transfer to bring to the handoff
        self._take_idx = 0         # next transfer to carry onward
        self._deliver_active = False
        self._take_active = False
        self._staged: int | None = None  # transfer whose block sits at the handoff
        self._hold_until: float | None = None

    # -- queries --------------------------------------------------------

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def tower_complete(self) -> bool:
        """True the instant the build phase has placed every block (before the
        admire beat and teardown begin)."""
        return (
            self._phase == "build"
            and self._take_idx >= len(self._transfers)
            and not self._take_active
        )

    # -- per-frame ------------------------------------------------------

    def update(self) -> None:
        if self._hold_until is not None:
            if time.perf_counter() >= self._hold_until:
                self._begin_teardown()
            return

        n = len(self._transfers)

        # 1. Deliver the next block to the handoff — only when the slot is free.
        if not self._deliver_active and self._staged is None and self._deliver_idx < n:
            t = self._transfers[self._deliver_idx]
            if not t.deliver.busy:
                t.deliver.queue(t.deliver.make_pick(t.color) + t.deliver.make_place(self.handoff))
                self._deliver_active = True

        # 2. Delivery finished → the block is staged at the handoff.
        if self._deliver_active and not self._transfers[self._deliver_idx].deliver.busy:
            self._staged = self._deliver_idx
            self._deliver_active = False
            self._deliver_idx += 1

        # 3. Carry the staged block onward. Freeing the slot here is safe: the
        #    take-arm lifts the block in ~2 s while the deliver-arm needs ~10 s
        #    (drive + pick + drive + place) to bring the next one — they can
        #    never collide at the slot.
        if not self._take_active and self._staged is not None:
            t = self._transfers[self._staged]
            if not t.take.busy:
                t.take.queue(t.take.make_pick(t.color) + t.take.make_place(t.dest))
                self._take_active = True
                self._staged = None

        # 4. Carry finished.
        if self._take_active and not self._transfers[self._take_idx].take.busy:
            self._take_active = False
            self._take_idx += 1

        # 5. Phase complete → admire then tear down, or loop back to building.
        if (
            self._take_idx >= n
            and not self._deliver_active
            and not self._take_active
            and self._staged is None
        ):
            if self._phase == "build":
                self._hold_until = time.perf_counter() + HOLD_S
            else:
                self._begin_build()
