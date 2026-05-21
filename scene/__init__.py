"""Scene rendering package — re-exports the public draw_* surface so
`from demo_live import scene` (and `scene.draw_arm(...)`) keeps working
unchanged. The implementation lives in:

  - `scene.arm`    arm pedestal / base / links / gripper / draw_arm
  - `scene.world`  ground, ball + trajectory, blocks
  - `scene.chrome` header / side panel / footer
"""

from .arm import draw_arm, draw_arm_base, draw_arm_pedestal
from .chrome import draw_footer, draw_header, draw_side_panel
from .world import (
    draw_ball,
    draw_blocks,
    draw_ground,
    draw_intercept_marker,
    draw_launch_preview,
    draw_trajectory,
)

__all__ = [
    "draw_arm",
    "draw_arm_base",
    "draw_arm_pedestal",
    "draw_ball",
    "draw_blocks",
    "draw_footer",
    "draw_ground",
    "draw_header",
    "draw_intercept_marker",
    "draw_launch_preview",
    "draw_side_panel",
    "draw_trajectory",
]
