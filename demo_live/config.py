"""Design tokens for Newton VLA Live Demo — Universal-Robots-inspired
industrial style.

Source of truth for colors, fonts, spacing. Referenced by every other module.

Two palettes coexist for backward compatibility:
  • Legacy academic-whiteboard tokens (PAPER, INK, PRIMARY, …) — still
    consumed by tests, research code, and a few non-rebuilt elements.
  • UR_* / INDUSTRIAL_* / LED_* tokens — used by the redesigned scene
    renderer for a UR-style white-and-blue collaborative-robot look.
"""

from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).parent
FONTS = ROOT / "fonts"

# ---------------------------------------------------------------- canvas
WIDTH = 1920
HEIGHT = 1080
FPS = 60

# Layout: main viewport on left, status panel on right
PANEL_WIDTH = 480
VIEWPORT_WIDTH = WIDTH - PANEL_WIDTH
HEADER_HEIGHT = 96
FOOTER_HEIGHT = 120

# ---------------------------------------------------------------- colors (academic whiteboard)
PAPER = (248, 250, 252)        # #F8FAFC - background
INK = (30, 41, 59)             # #1E293B - primary text & lines
INK_SOFT = (100, 116, 139)     # slate-500 - secondary text
PRIMARY = (37, 99, 235)        # #2563EB - highlights
SECONDARY = (59, 130, 246)     # #3B82F6 - active state
ACCENT = (249, 115, 22)        # #F97316 - CTA / warning
GRID = (226, 232, 240)         # slate-200 - subtle grid lines

# Block / object colors
RED = (239, 68, 68)            # red-500
GREEN = (34, 197, 94)          # green-500
BLUE = (59, 130, 246)          # blue-500
YELLOW = (234, 179, 8)         # yellow-500
# Arm B's dedicated "workpiece" — a deliberately desaturated industrial
# grey so the audience reads it as "machine part, not toy" and doesn't
# confuse it with the four primary teaching colours. Also: NOT in
# `KNOWN_COLORS` (vla.py), so voice commands can't accidentally hijack it.
WORKPIECE = (148, 152, 158)

BLOCK_COLORS = {
    "red": RED,
    "green": GREEN,
    "blue": BLUE,
    "yellow": YELLOW,
    "workpiece": WORKPIECE,
}

# ---------------------------------------------------------------- UR industrial palette
# Universal-Robots-inspired tokens used by the redesigned scene renderer.
# Off-white machine bodies, dark joint housings, cool cyan-blue accents,
# light industrial floor.

UR_BODY              = (252, 252, 250)
UR_BODY_SHADOW       = (224, 226, 230)
UR_BODY_OUTLINE      = (180, 184, 190)
UR_JOINT_HOUSING     = (32, 35, 40)
UR_JOINT_FACE        = (60, 64, 70)
UR_ACCENT            = (24, 144, 192)
UR_ACCENT_SOFT       = (160, 200, 220)
UR_BOLT              = (80, 84, 90)
UR_CABLE             = (45, 48, 55)

INDUSTRIAL_FLOOR     = (236, 238, 240)
INDUSTRIAL_FLOOR_LINE = (216, 220, 226)   # lightened to a hairline so the faded grid recedes
INDUSTRIAL_INK       = (38, 42, 48)
INDUSTRIAL_INK_SOFT  = (130, 138, 148)

# Soft top-to-floor studio backdrop + top-lit sheen for a "rendered" look.
BACKDROP_TOP         = (245, 247, 249)    # gradient top (above-ground air); falls to INDUSTRIAL_FLOOR at the floor
UR_BODY_HILIGHT      = (255, 255, 254)    # bright top-edge rim on white machine bodies / cubes

PANEL_BG             = (248, 249, 251)
PANEL_BORDER         = (210, 214, 222)

LED_GREEN            = (88, 196, 122)
LED_AMBER            = (240, 178, 64)
LED_RED              = (220, 84, 84)

# Machined-plastic block tones. Less saturated than the legacy primary
# colours, so the parts don't dominate the off-white machinery.
BLOCK_RED    = (224, 96, 96)
BLOCK_GREEN  = (96, 184, 124)
BLOCK_BLUE   = (88, 152, 220)
BLOCK_YELLOW = (236, 196, 92)
# Workpiece tone — slightly warmer industrial grey to stand out from the
# off-white machinery without competing with the four primary parts.
BLOCK_WORKPIECE = (138, 142, 150)

UR_BLOCK_COLORS = {
    "red": BLOCK_RED,
    "green": BLOCK_GREEN,
    "blue": BLOCK_BLUE,
    "yellow": BLOCK_YELLOW,
    "workpiece": BLOCK_WORKPIECE,
}

# ---------------------------------------------------------------- world scale
# Newton uses meters. Map to pixels: 1 m = 180 px. Ground at y=0.
PX_PER_M = 180.0
# Origin of the viewport: arm base rests on the ground, centered horizontally.
GROUND_Y_PX = HEIGHT - FOOTER_HEIGHT - 60     # pixels from top
ORIGIN_X_PX = VIEWPORT_WIDTH // 2 - 160       # pixels from left

# World-frame arm base position (arm is anchored above ground on a small pedestal)
ARM_BASE_Z = 0.6  # meters above ground

# Canonical spawn layout: (color, world-x of the block center, z offset).
# Single source of truth shared by physics.World (body/teleport placement)
# and vla.py (the keyword parser's drive targets + Claude's system prompt) —
# keep newton-free so the parser stays importable without the engine.
# 0.4 m centers → 0.2 m gap between 0.20 m cubes; the workpiece lives in
# Arm B's reach zone (anchor x=2.40) away from the four teaching colors.
BLOCK_LAYOUT: tuple[tuple[str, float, float], ...] = (
    ("red", 0.70, 0.0),
    ("green", 1.10, 0.0),
    ("blue", 1.50, 0.0),
    ("yellow", -0.95, 0.0),
    ("workpiece", 2.00, 0.0),
)

# All viewport pixel distances scale with this; bump up for classroom visibility.

# ---------------------------------------------------------------- typography
FONT_HEADING = str(FONTS / "Kalam-Bold.ttf")
FONT_BODY = str(FONTS / "PatrickHand-Regular.ttf")
FONT_ACCENT = str(FONTS / "Kalam-Regular.ttf")

SIZE_H1 = 42
SIZE_H2 = 28
SIZE_BODY = 22
SIZE_LARGE = 32
SIZE_SMALL = 18
SIZE_MONO = 20

# ---------------------------------------------------------------- hand-drawn style params
# Lines get a little wobble to feel like chalk / marker, not CAD.
WOBBLE = 0.6            # pixels of perpendicular jitter per segment
LINE_WIDTH_THICK = 6    # arm links
LINE_WIDTH_MEDIUM = 4   # blocks, ground
LINE_WIDTH_THIN = 2     # grid, annotations

# ---------------------------------------------------------------- demo modes
MODE_IDLE = "idle"
MODE_BALL_CATCH = "ball_catch"
MODE_VLA = "vla"
