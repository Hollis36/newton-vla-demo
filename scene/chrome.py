"""Scene "chrome" layer: header, side panel, footer.

These are the UI affordances that frame the workspace — branding,
mode/FPS, status lines, parsed-VLA JSON, and the input prompt. The
workspace drawables (arm, blocks, ball, ground) live in `scene.world`.
"""

from __future__ import annotations

import math

import pygame

from .. import config as C
from .. import render as R


def draw_header(surface: pygame.Surface, mode_label: str, fps: float) -> None:
    """Industrial chrome header. White backplate, hairline divider,
    NEWTON · LIVE wordmark on the left, UR-cyan filled mode chip + fps
    counter on the right."""
    # Header backplate (PANEL_BG, slightly lighter than the floor) so the
    # chrome separates cleanly from the workspace.
    pygame.draw.rect(surface, C.PANEL_BG,
                     (0, 0, C.WIDTH, C.HEADER_HEIGHT))
    # Hairline divider.
    pygame.draw.line(surface, C.PANEL_BORDER,
                     (0, C.HEADER_HEIGHT - 1),
                     (C.WIDTH, C.HEADER_HEIGHT - 1), 1)
    # Cyan accent line just below the divider — a UR design tic.
    pygame.draw.line(surface, C.UR_ACCENT,
                     (0, C.HEADER_HEIGHT),
                     (260, C.HEADER_HEIGHT), 2)

    # Left: wordmark + tagline.
    R.text(surface, "NEWTON · LIVE", (40, 22),
           size=C.SIZE_H1, color=C.INDUSTRIAL_INK, font_path=C.FONT_HEADING)
    R.text(surface, "EMBODIED AI WORKSTATION", (40, 70),
           size=C.SIZE_SMALL, color=C.INDUSTRIAL_INK_SOFT, font_path=C.FONT_BODY)

    # Right: cyan-pill mode chip.
    chip_w = 240
    chip_h = 38
    chip_x = C.WIDTH - 40 - chip_w
    chip_y = 22
    R.aa_rounded_rect(surface, fill=C.UR_ACCENT, outline=None,
                      rect=(chip_x, chip_y, chip_w, chip_h),
                      radius=chip_h // 2)
    R.text(surface, f"MODE · {mode_label}",
           (chip_x + chip_w // 2, chip_y + chip_h // 2),
           size=C.SIZE_BODY, color=C.UR_BODY,
           font_path=C.FONT_HEADING, anchor="center")
    # FPS counter under the chip.
    R.text(surface, f"{fps:5.1f} fps",
           (C.WIDTH - 40, chip_y + chip_h + 8),
           size=C.SIZE_SMALL, color=C.INDUSTRIAL_INK_SOFT,
           font_path=C.FONT_BODY, anchor="tr")


def draw_side_panel(
    surface: pygame.Surface,
    status_lines: list[str],
    recent_commands: list[str] | None = None,
    parsed_json: dict | None = None,
) -> None:
    """Industrial technical-UI side panel: PANEL_BG fill, hairline border,
    section headers in caps with cyan underline, status entries in plain
    text, parsed-JSON in a dark code-block."""
    x0 = C.VIEWPORT_WIDTH
    # Panel backplate covers full panel rect.
    pygame.draw.rect(surface, C.PANEL_BG,
                     (x0, C.HEADER_HEIGHT, C.PANEL_WIDTH,
                      C.HEIGHT - C.HEADER_HEIGHT - C.FOOTER_HEIGHT))
    # Hairline left border.
    pygame.draw.line(surface, C.PANEL_BORDER,
                     (x0, C.HEADER_HEIGHT),
                     (x0, C.HEIGHT - C.FOOTER_HEIGHT), 1)

    def _section_header(label: str, y: int) -> int:
        R.text(surface, label, (x0 + 28, y),
               size=C.SIZE_BODY, color=C.INDUSTRIAL_INK,
               font_path=C.FONT_HEADING)
        # Cyan underline.
        pygame.draw.line(surface, C.UR_ACCENT,
                         (x0 + 28, y + 26),
                         (x0 + 28 + 36, y + 26), 2)
        # Hairline divider further right.
        pygame.draw.line(surface, C.PANEL_BORDER,
                         (x0 + 80, y + 26),
                         (C.WIDTH - 28, y + 26), 1)
        return y + 42

    # CONTROLS
    y = C.HEADER_HEIGHT + 22
    y = _section_header("CONTROLS", y)
    bindings = [
        ("1", "Ball catch · MPC"),
        ("2", "Type command · VLA"),
        ("3", "Speak command"),
        ("R", "Reset scene"),
        ("Q", "Quit"),
    ]
    for key, desc in bindings:
        # Cyan-outlined key chip.
        chip = pygame.Rect(x0 + 28, y, 36, 32)
        R.aa_rounded_rect(surface,
                          fill=C.UR_BODY, outline=C.UR_ACCENT,
                          rect=tuple(chip), radius=4, width=2)
        R.text(surface, key, chip.center,
               size=C.SIZE_BODY, color=C.UR_ACCENT,
               font_path=C.FONT_HEADING, anchor="center")
        R.text(surface, desc, (x0 + 78, y + 4),
               size=C.SIZE_SMALL, color=C.INDUSTRIAL_INK,
               font_path=C.FONT_BODY)
        y += 42

    # AI THINKING — parsed JSON in a dark code-block. We show up to 7 fields
    # (user, via, action, color, colors, target, reason) so the audience can
    # follow the chain user-input → backend → parsed-output without a debug
    # console open.
    if parsed_json is not None:
        y += 6
        y = _section_header("AI · PARSED", y)
        max_rows = 7
        row_h = 18
        block_h = 12 + max_rows * row_h
        pygame.draw.rect(surface, C.UR_JOINT_HOUSING,
                         (x0 + 28, y, C.PANEL_WIDTH - 56, block_h))
        pygame.draw.rect(surface, C.UR_BOLT,
                         (x0 + 28, y, C.PANEL_WIDTH - 56, block_h), 1)
        lines = [(k, v) for k, v in parsed_json.items() if v is not None]
        yy = y + 8
        for k, v in lines[:max_rows]:
            # Cyan key, white value (clipped). Wider clip (36) so longer
            # reasons / user inputs aren't truncated mid-word.
            R.text(surface, f'"{k}":',
                   (x0 + 38, yy),
                   size=C.SIZE_SMALL, color=C.UR_ACCENT,
                   font_path=C.FONT_HEADING)
            value_str = str(v)[:36]
            R.text(surface, value_str,
                   (x0 + 130, yy),
                   size=C.SIZE_SMALL, color=C.UR_BODY,
                   font_path=C.FONT_BODY)
            yy += row_h
        y += block_h + 8

    # RECENT COMMANDS
    if recent_commands:
        y = _section_header("RECENT COMMANDS", y)
        yy = y
        for line in recent_commands[-3:]:
            R.text(surface, f"› {line[:30]}",
                   (x0 + 28, yy),
                   size=C.SIZE_SMALL, color=C.INDUSTRIAL_INK,
                   font_path=C.FONT_BODY)
            yy += 22
        y = yy + 6

    # STATUS LOG
    y = _section_header("STATUS LOG", y)
    yy = y
    for line in status_lines[-6:]:
        R.text(surface, line[:42],
               (x0 + 28, yy),
               size=C.SIZE_SMALL, color=C.INDUSTRIAL_INK_SOFT,
               font_path=C.FONT_BODY)
        yy += 22


def draw_footer(
    surface: pygame.Surface,
    prompt: str,
    input_text: str,
    input_active: bool,
    thinking: bool = False,
    listening: bool = False,
) -> None:
    y0 = C.HEIGHT - C.FOOTER_HEIGHT
    pygame.draw.rect(surface, C.PANEL_BG,
                     (0, y0, C.WIDTH, C.FOOTER_HEIGHT))
    pygame.draw.line(surface, C.UR_ACCENT, (0, y0), (C.WIDTH, y0), 2)
    pygame.draw.line(surface, C.PANEL_BORDER,
                     (0, C.HEIGHT - 1), (C.WIDTH, C.HEIGHT - 1), 1)

    # Prompt label.
    R.text(surface, prompt, (40, y0 + 16),
           size=C.SIZE_SMALL, color=C.INDUSTRIAL_INK_SOFT,
           font_path=C.FONT_BODY)

    # Input box.
    box = pygame.Rect(40, y0 + 46, C.WIDTH - 80, 56)
    if thinking:
        outline = C.LED_AMBER
    elif listening:
        outline = C.LED_GREEN
    elif input_active:
        outline = C.UR_ACCENT
    else:
        outline = C.PANEL_BORDER
    R.aa_rounded_rect(surface,
                      fill=C.UR_BODY, outline=outline,
                      rect=tuple(box), radius=8, width=2)

    if listening:
        t = pygame.time.get_ticks() / 120
        mic_x = box.x + 36
        mic_y = box.centery
        pygame.draw.circle(surface, C.UR_ACCENT, (mic_x, mic_y), 14)
        pygame.draw.circle(surface, C.INDUSTRIAL_INK, (mic_x, mic_y), 14, 2)
        pygame.draw.line(surface, C.UR_BODY,
                         (mic_x - 6, mic_y - 2), (mic_x - 6, mic_y + 4), 3)
        pygame.draw.line(surface, C.UR_BODY,
                         (mic_x + 6, mic_y - 2), (mic_x + 6, mic_y + 4), 3)
        for i in range(18):
            bar_x = box.x + 80 + i * 18
            amp = 8 + 14 * abs(math.sin(t + i * 0.4))
            pygame.draw.line(surface, C.UR_ACCENT,
                             (bar_x, box.centery - amp),
                             (bar_x, box.centery + amp), 4)
        R.text(surface, "LISTENING",
               (box.right - 28, box.centery - 12),
               size=C.SIZE_BODY, color=C.UR_ACCENT,
               font_path=C.FONT_HEADING, anchor="tr")
    elif thinking:
        dots = 1 + (pygame.time.get_ticks() // 300) % 3
        label = "ANALYZING" + "." * dots
        R.text(surface, label, (box.x + 20, box.centery - 14),
               size=C.SIZE_BODY, color=C.LED_AMBER,
               font_path=C.FONT_HEADING)
    else:
        blink_on = input_active and (pygame.time.get_ticks() // 500) % 2 == 0
        cursor = "_" if blink_on else ""
        R.text(surface, f">> {input_text}{cursor}",
               (box.x + 20, box.centery - 14),
               size=C.SIZE_BODY, color=C.INDUSTRIAL_INK,
               font_path=C.FONT_BODY)
