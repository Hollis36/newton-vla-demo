"""Newton VLA Live Demo — embodied AI on a MacBook.

A 3-minute classroom demonstration combining the NVIDIA Newton XPBD
physics engine, a 2D pygame UI, and Claude's command-line client as
the Vision-Language-Action brain.

Three interaction modes:
    * MPC ball catching (closed-form ballistic intercept, no AI)
    * Natural-language pick / place / stack via Claude with a 1 ms
      keyword preflight that runs in parallel so the arm never waits
    * Decorative gestures (wave / point / bow / dance)

Optional `--industrial` flag adds a second fixed-base arm that
perpetually shuttles a workpiece block, demonstrating multi-agent
coordination over a shared world without contention.

See `README.md` for the command vocabulary and `REHEARSAL.md` for the
3-minute on-stage script. Reach out via the GitHub issue tracker:
https://github.com/Hollis36/newton-vla-demo/issues
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "kingcode (Hollis36)"
__license__ = "MIT"
__url__ = "https://github.com/Hollis36/newton-vla-demo"

# Public re-exports — the demo is normally launched as
# `python -m demo_live` so most users never `import demo_live.something`
# directly, but the symbols below are convenient for embedding the
# components into a notebook or a custom rig.

__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "__url__",
]
