"""Tests for the opt-in real-blocks physics path (World(real_blocks=True)).

The default teleport path is covered elsewhere (test_tasks, test_pipeline).
These lock the genuine-rigid-body behavior: kinematic-grasp follow, release +
settle, real stacking, and the safety guards (double-grab, release-without-grab,
out-of-bounds-while-held) — plus a check that teleport mode is unaffected.

Newton prints kernel-load chatter to stdout on first use; we redirect it so the
unittest output stays readable.
"""

from __future__ import annotations

import contextlib
import io
import unittest

import newton
import numpy as np

from demo_live.physics import BLOCK_HALF, World


@contextlib.contextmanager
def _quiet():
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def _world(**kwargs) -> World:
    with _quiet():
        return World(**kwargs)


def _settle(world: World, frames: int = 30) -> None:
    with _quiet():
        for _ in range(frames):
            world.step()


class TeleportModeUnaffected(unittest.TestCase):
    """The default path must gain no rigid bodies and treat grasp as a no-op."""

    def test_blocks_have_no_body_and_grasp_is_noop(self):
        world = _world()  # default: real_blocks=False
        self.assertTrue(all(b.body_id is None for b in world.blocks))
        red = world.find_block("red")
        world.grab_block(red)  # must not raise, must not "hold" anything
        self.assertFalse(world.is_block_held(red))
        world.release_block(red)  # release-without-grab must be safe


class RealBlocksConstruction(unittest.TestCase):
    def test_each_block_gets_a_body_and_settles_on_the_ground(self):
        world = _world(real_blocks=True)
        self.assertTrue(all(b.body_id is not None for b in world.blocks))
        _settle(world)
        for b in world.blocks:
            self.assertAlmostEqual(b.xz[1], BLOCK_HALF, delta=0.03,
                                   msg=f"{b.color} did not settle on the ground")


class RealBlocksGrasp(unittest.TestCase):
    def test_held_block_follows_prescribed_pose_and_does_not_fall(self):
        world = _world(real_blocks=True)
        _settle(world, 10)
        red = world.find_block("red")
        world.grab_block(red)
        self.assertTrue(world.is_block_held(red))
        with _quiet():
            for z in np.linspace(BLOCK_HALF, 0.8, 40):
                world.move_block(red, (0.5, float(z)))
                world.step()
        self.assertAlmostEqual(red.xz[0], 0.5, delta=0.02)
        self.assertGreater(red.xz[1], 0.7, "kinematic held block should not fall")

    def test_released_block_falls_and_settles(self):
        world = _world(real_blocks=True)
        _settle(world, 10)
        red = world.find_block("red")
        world.grab_block(red)
        world.move_block(red, (0.5, 0.8))
        with _quiet():
            world.step()
            world.release_block(red)
            for _ in range(150):
                world.step()
        self.assertFalse(world.is_block_held(red))
        self.assertAlmostEqual(red.xz[1], BLOCK_HALF, delta=0.04,
                               msg="released block should fall to the ground")

    def test_double_grab_and_release_without_grab_are_safe(self):
        world = _world(real_blocks=True)
        red = world.find_block("red")
        world.grab_block(red)
        world.grab_block(red)  # second grab — no-op, must not corrupt the flag
        self.assertEqual(int(world.model.body_flags.numpy()[red.body_id]),
                         int(newton.BodyFlags.KINEMATIC))
        self.assertTrue(world.is_block_held(red))
        world.release_block(red)
        world.release_block(red)  # release-without-grab — no-op
        self.assertEqual(int(world.model.body_flags.numpy()[red.body_id]),
                         int(newton.BodyFlags.DYNAMIC))
        self.assertFalse(world.is_block_held(red))


class OutOfBoundsRecovery(unittest.TestCase):
    """World.recover_out_of_bounds snaps flung blocks home but never fights a
    block the gripper is carrying (the docstring promise of this module)."""

    def test_recovery_skips_held_block_then_applies_after_release(self):
        world = _world(real_blocks=True)
        _settle(world, 10)
        red = world.find_block("red")
        spawn_x = red.xz[0]
        world.grab_block(red)
        world.move_block(red, (5.0, 1.0))  # way out of bounds, mid-carry
        world.recover_out_of_bounds()
        self.assertAlmostEqual(red.xz[0], 5.0, delta=0.01,
                               msg="held block must never be snapped to spawn")
        world.release_block(red)
        world.recover_out_of_bounds()
        self.assertAlmostEqual(red.xz[0], spawn_x, delta=0.01,
                               msg="released OOB block should return to spawn")

    def test_recovery_teleport_mode_snaps_stray_block_home(self):
        world = _world()  # teleport mode
        red = world.find_block("red")
        spawn = red.xz
        world.move_block(red, (-9.0, 0.4))
        world.recover_out_of_bounds()
        self.assertEqual(red.xz, spawn)

    def test_recovery_leaves_in_bounds_blocks_alone(self):
        world = _world()
        red = world.find_block("red")
        world.move_block(red, (1.9, BLOCK_HALF))  # unusual but in bounds
        world.recover_out_of_bounds()
        self.assertAlmostEqual(red.xz[0], 1.9, delta=0.01)


class RealBlocksStacking(unittest.TestCase):
    def test_block_placed_on_another_rests_on_top(self):
        world = _world(real_blocks=True)
        _settle(world, 20)
        base = world.find_block("red")
        top = world.find_block("green")
        place_x = -0.40
        with _quiet():
            # Seat the base at a clear spot via a grasp cycle.
            world.grab_block(base)
            for _ in range(10):
                world.move_block(base, (place_x, BLOCK_HALF))
                world.step()
            world.release_block(base)
            for _ in range(20):
                world.step()
            # Carry the top above the base and release onto it.
            world.grab_block(top)
            for _ in range(20):
                world.move_block(top, (place_x, 3 * BLOCK_HALF + 0.03))
                world.step()
            world.release_block(top)
            for _ in range(150):
                world.step()
        self.assertAlmostEqual(base.xz[1], BLOCK_HALF, delta=0.05)
        self.assertAlmostEqual(top.xz[1], 3 * BLOCK_HALF, delta=0.07,
                               msg="top block should rest one block-height above the base")
        self.assertAlmostEqual(top.xz[0], place_x, delta=0.12)


if __name__ == "__main__":
    unittest.main()
