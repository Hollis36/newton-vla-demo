"""Closed-form IK for a 3-link planar arm (revolute, all around the same axis).

The 3rd DOF is redundant for positioning a point, so we let the caller specify
the desired **hand (gripper) orientation** in world — usually -pi/2 for
pointing down (grasping a cube from above). This reduces the problem to a
standard 2-link IK on the "wrist" position.

All angles are in radians, all positions in meters, in the arm's world frame.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from . import config as C
from .physics import LINK_LENGTHS


class IKResult(NamedTuple):
    ok: bool
    q: tuple[float, float, float]
    reach_ratio: float    # |target - base| / TOTAL_REACH ; >1 means unreachable


def solve_ik(
    target_x: float,
    target_z: float,
    hand_angle: float = -math.pi / 2,
    elbow_up: bool = True,
) -> IKResult:
    """Compute (q0, q1, q2) that place the arm tip at (target_x, target_z).

    `hand_angle` is the world-frame orientation of the final link
    (sum of all joint angles). Default -pi/2 = pointing straight down.
    """
    L0, L1, L2 = LINK_LENGTHS

    # Arm base is at (0, ARM_BASE_Z) in world.
    bx, bz = 0.0, C.ARM_BASE_Z

    # Project target back along hand direction to get the "wrist" (end of L1).
    wx = target_x - L2 * math.cos(hand_angle)
    wz = target_z - L2 * math.sin(hand_angle)

    # Relative to arm base.
    dx = wx - bx
    dz = wz - bz
    d2 = dx * dx + dz * dz
    d = math.sqrt(d2)
    reach_ratio = d / (L0 + L1)
    if d > L0 + L1 or d < abs(L0 - L1):
        # Clamp to reachable circle; still return a best-effort pose.
        d_clamped = max(abs(L0 - L1) + 1e-3, min(L0 + L1 - 1e-3, d))
        scale = d_clamped / (d + 1e-9)
        dx, dz = dx * scale, dz * scale
        d2 = dx * dx + dz * dz
        d = d_clamped
        reachable = False
    else:
        reachable = True

    cos_q1 = (d2 - L0 * L0 - L1 * L1) / (2 * L0 * L1)
    cos_q1 = max(-1.0, min(1.0, cos_q1))
    q1 = math.acos(cos_q1)
    if not elbow_up:
        q1 = -q1

    q0 = math.atan2(dz, dx) - math.atan2(L1 * math.sin(q1), L0 + L1 * math.cos(q1))
    q2 = hand_angle - q0 - q1

    # Normalize angles to [-pi, pi].
    def wrap(a: float) -> float:
        return (a + math.pi) % (2 * math.pi) - math.pi

    return IKResult(
        ok=reachable,
        q=(wrap(q0), wrap(q1), wrap(q2)),
        reach_ratio=reach_ratio,
    )


def forward_kinematics(q0: float, q1: float, q2: float) -> tuple[float, float, float]:
    """(x, z, hand_angle) for a given joint configuration."""
    L0, L1, L2 = LINK_LENGTHS
    th0 = q0
    th1 = q0 + q1
    th2 = q0 + q1 + q2
    x = L0 * math.cos(th0) + L1 * math.cos(th1) + L2 * math.cos(th2)
    z = C.ARM_BASE_Z + L0 * math.sin(th0) + L1 * math.sin(th1) + L2 * math.sin(th2)
    return x, z, th2
