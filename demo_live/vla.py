"""Vision-Language-Action layer.

Turns a natural-language command into a typed task plan that the
TaskExecutor can run. The LLM backend is the user's `claude` CLI invoked as
a subprocess (so no separate API key is needed). We wrap it with a
conservative timeout + JSON schema, and fall back to a keyword parser if
the CLI is unavailable, slow, or returns malformed JSON — the demo must
never hang on-stage.

Returned action schema:
{
  "action": "pick" | "place" | "stack" | "home" | "unknown",
  "color":  "red" | "green" | "blue" | "yellow" | null,
  "colors": [...] | null,          # for "stack"
  "target": [x, z] | null,         # world coordinates for "place"
  "reason": "human-readable explanation of the parse"
}
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any

KNOWN_COLORS = ("red", "green", "blue", "yellow")

# Every action the parser may emit. Single source of truth shared by the
# field sanitizer, the API tool schema, and the eval harness.
KNOWN_ACTIONS = (
    "pick", "place", "stack", "drive", "home",
    "wave", "point", "bow", "dance", "unknown",
)

# ----------------------------------------------------------------- backends
# The VLA layer has three interchangeable language backends, all reconciled
# to the same action schema and the same keyword fallback:
#
#   "cli"     — `claude --print` subprocess. No API key, no Python deps.
#               This is the project default and what every rehearsed command
#               is tuned against.
#   "api"     — the Anthropic Python SDK with forced tool-use (guaranteed
#               valid structured output, no regex parsing) + a cache-marked
#               system prompt. Opt in with NEWTON_VLA_BACKEND=api and an
#               ANTHROPIC_API_KEY. One HTTP round-trip instead of booting a
#               Node CLI, so noticeably lower per-call latency.
#   "keyword" — deterministic offline parser only (the live-safety net).
#   "learned" — a pluggable learned intent policy (see `policy.py`).
#
# Any backend that returns nothing falls through to the keyword parser, so
# the demo can never hang on-stage regardless of which one is selected.
DEFAULT_BACKEND = os.environ.get("NEWTON_VLA_BACKEND", "cli")

# Model selection is a single knob shared by the CLI and API backends. It
# accepts a short alias ("sonnet" / "haiku" / "opus") — which the `claude`
# CLI understands directly — or a fully-qualified model id. The default
# preserves the project's original `--model sonnet` choice: a fast model
# matters for an on-stage demo, and Sonnet already nails the vocabulary.
DEFAULT_MODEL = os.environ.get("NEWTON_VLA_MODEL", "sonnet")

# Alias → fully-qualified id, used when a backend needs a concrete model
# string (the API SDK does; the CLI resolves aliases itself). Kept current
# with the latest Claude family.
_MODEL_ALIASES = {
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
    "opus": "claude-opus-4-8",
}


def _resolve_model_id(model: str) -> str:
    """Resolve a short alias to a fully-qualified Claude model id, or pass a
    model string through unchanged if it isn't a known alias."""
    return _MODEL_ALIASES.get(model, model)

# Chinese → English color aliases. Longer strings matched first (红色 before 红)
# so substring checks don't double-count.
CHINESE_COLOR_MAP: tuple[tuple[str, str], ...] = (
    ("红色", "red"), ("红", "red"),
    ("绿色", "green"), ("绿", "green"),
    ("蓝色", "blue"), ("蓝", "blue"),
    ("黄色", "yellow"), ("黄", "yellow"),
)

SYSTEM_PROMPT = """You are the intent parser for a mobile robot (tracked
base + 3-DOF arm + gripper) demo.

The input may come from a noisy speech recognizer, so be LIBERAL about
interpretation. Common mishears you should tolerate:
  - "peter / pete / pink / bic"  → "pick"
  - "ride / read / rad / ready"  → "red"
  - "grain / grin / clean"       → "green"
  - "blew / glue / below"        → "blue"
  - "mellow / fellow / hello"    → "yellow"
  - "stuck / stick / tar / stocks / star" → "stack"
  - "flower / power / hour"      → "tower"
  - "drive / move / go / roll / travel" → "drive"

Convert the user's utterance into ONE JSON object with these fields:

  action: one of "pick", "place", "stack", "drive", "home",
                 "wave", "point", "bow", "dance", "unknown"
  color:  one of red / green / blue / yellow, or null
  colors: array of 2-4 of those colors (only for action="stack");
          for action="point", a single-element array of
          "left" | "right" | "audience" picks the gesture direction; else null
  target: [x, z] in meters (world frame), or null.
          For action="drive", only the x matters; z is 0.
  reason: a short human explanation (under 80 chars).

Gestures are decorative — pick them when the user asks the robot to "wave",
"say hi", "point at X", "bow", or "dance". No color / target needed.

World layout:
  - Tracked mobile base. Base world x starts at 0. Valid drive range x ∈ [-1.6, +1.6].
  - Arm lives on top of the base. Blocks sit on the ground.
  - Red starts at x=+0.9, green +1.1, blue +1.3, yellow -0.9.
  - "Stack" puts the first color on the ground at x=-0.40, then stacks
    the rest on top.
  - Valid "place" targets are x ∈ [-1.1, 1.3], z ∈ [0, 0.3].
  - "drive" moves the base. "left" = x decreases, "right" = x increases.
    "drive to red" = move base near the red block. Use relative moves
    of 0.5–0.8 m when direction is given without a number.

Only output JSON. No prose. No markdown fences. Examples:

User: pick up the green cube
Output: {"action":"pick","color":"green","colors":null,"target":null,"reason":"asked to pick green"}

User: peter ride
Output: {"action":"pick","color":"red","colors":null,"target":null,"reason":"heard 'peter ride' → 'pick red'"}

User: drive left
Output: {"action":"drive","color":null,"colors":null,"target":[-0.6,0],"reason":"move base left by 0.6"}

User: go to the blue block
Output: {"action":"drive","color":null,"colors":null,"target":[1.0,0],"reason":"drive near blue at x=1.3"}

User: move right two meters
Output: {"action":"drive","color":null,"colors":null,"target":[1.6,0],"reason":"drive 2m right (clamped)"}

User: build a tower
Output: {"action":"stack","color":null,"colors":["red","green","blue"],"target":null,"reason":"default tower"}

User: 拿起红色方块
Output: {"action":"pick","color":"red","colors":null,"target":null,"reason":"Chinese: pick red"}

User: 搭一个塔
Output: {"action":"stack","color":null,"colors":["red","green","blue"],"target":null,"reason":"Chinese: default tower"}

User: 把蓝色方块放到左边
Output: {"action":"place","color":"blue","colors":null,"target":[-0.6,0],"reason":"Chinese: place blue on the left"}

User: 开到绿色方块旁边
Output: {"action":"drive","color":null,"colors":null,"target":[0.88,0],"reason":"Chinese: drive near green"}

User: 往右走一米
Output: {"action":"drive","color":null,"colors":null,"target":[1.0,0],"reason":"Chinese: drive right 1m"}

User: 回家 / 回位
Output: {"action":"home","color":null,"colors":null,"target":null,"reason":"Chinese: return home"}

User: sdfgsdfg
Output: {"action":"unknown","color":null,"colors":null,"target":null,"reason":"could not parse"}
"""


@dataclass
class VLAResult:
    action: str
    color: str | None = None
    colors: list[str] | None = None
    target: tuple[float, float] | None = None
    reason: str = ""
    source: str = "fallback"    # "claude" or "fallback"
    latency_ms: float = 0.0


def _format_history(history: list[tuple[str, dict[str, Any]]] | None) -> str:
    """Render the last few (user_input, parsed_result) pairs into a few lines
    of context that go into the prompt, so Claude can resolve references like
    'do it again', 'now with green', 'stack them'."""
    if not history:
        return ""
    lines = ["Recent commands (most recent last):"]
    for prev_input, prev_data in history[-3:]:
        action = prev_data.get("action", "?")
        color = prev_data.get("color")
        colors = prev_data.get("colors")
        target = prev_data.get("target")
        bits = [f"action={action}"]
        if color:
            bits.append(f"color={color}")
        if colors:
            bits.append(f"colors={colors}")
        if target:
            bits.append(f"target={target}")
        lines.append(f'  user said "{prev_input}" → {", ".join(bits)}')
    return "\n".join(lines) + "\n\n"


def _format_world(world_state: dict[str, Any] | None) -> str:
    """Render the current scene state into a few lines of context. Lets the
    LLM disambiguate spatial references ('the leftmost one', 'whatever I'm
    holding now'). World state is opt-in — None means 'no scene context'."""
    if not world_state:
        return ""
    lines = ["Current scene:"]
    base_x = world_state.get("base_x")
    if base_x is not None:
        lines.append(f"  robot base is at x={base_x:+.2f}")
    held = world_state.get("held_color")
    if held:
        lines.append(f"  gripper is holding the {held} block")
    else:
        lines.append("  gripper is empty")
    blocks = world_state.get("blocks") or []
    if blocks:
        positions = ", ".join(f"{c}({x:+.2f}, {z:+.2f})" for c, x, z in blocks)
        lines.append(f"  blocks on field: {positions}")
    return "\n".join(lines) + "\n\n"


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Return the first complete top-level JSON object in `text`, or None.

    Replaces a greedy ``re.search(r"\\{.*\\}")`` that matched from the first
    ``{`` to the *last* ``}`` in the output — which silently merged two
    objects or swept up trailing prose that happened to contain a brace.
    This scans for the first *balanced* ``{...}`` (string- and escape-aware,
    so braces inside string values don't confuse the depth counter) and
    ``json.loads`` it. Anything that isn't a parseable object yields None,
    matching the old contract the subprocess tests lock in."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
                return obj if isinstance(obj, dict) else None
    return None


def _call_claude_cli(
    user_input: str,
    timeout: float = 8.0,
    history: list[tuple[str, dict[str, Any]]] | None = None,
    world_state: dict[str, Any] | None = None,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Invoke `claude --print` with the user's command and parse JSON out.

    Optional `history` and `world_state` are injected into the prompt as
    context so Claude can resolve cross-turn references ('do it again',
    'now green', 'put that one back') and spatial references ('the
    leftmost cube'). `model` overrides the default model alias (the CLI
    accepts "sonnet" / "haiku" / "opus" or a full id)."""
    if shutil.which("claude") is None:
        return None
    context = _format_history(history) + _format_world(world_state)
    prompt = f"{SYSTEM_PROMPT}\n\n{context}User: {user_input}\nOutput:"
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", model or DEFAULT_MODEL],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    out = result.stdout.strip()
    # Strip accidental markdown fencing, then pull out the first *balanced*
    # JSON object (the scanner tolerates leftover fences and trailing prose).
    out = re.sub(r"^```(?:json)?\s*", "", out)
    out = re.sub(r"\s*```$", "", out)
    return _extract_json_object(out)


# Tool schema for the API backend. Forcing this tool (`tool_choice`) makes
# Claude return its parse as a structured `tool_use` block — no free-text
# JSON to regex out, no markdown fences to strip. Fields mirror the action
# schema; `parse_command` still sanitizes everything downstream.
_PARSE_TOOL: dict[str, Any] = {
    "name": "emit_robot_action",
    "description": "Emit the single parsed robot action for the user's command.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(KNOWN_ACTIONS),
                "description": "The robot action to perform.",
            },
            "color": {
                "type": ["string", "null"],
                "description": "Target block colour for pick, or null.",
            },
            "colors": {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "Colours for stack, or [left|right|audience] for point.",
            },
            "target": {
                "type": ["array", "null"],
                "items": {"type": "number"},
                "description": "[x, z] world coordinates for place/drive, or null.",
            },
            "reason": {
                "type": "string",
                "description": "Short human explanation of the parse (<80 chars).",
            },
        },
        "required": ["action", "reason"],
    },
}


def _call_anthropic_api(
    user_input: str,
    timeout: float = 8.0,
    history: list[tuple[str, dict[str, Any]]] | None = None,
    world_state: dict[str, Any] | None = None,
    model: str | None = None,
) -> dict[str, Any] | None:
    """Parse `user_input` via the Anthropic Python SDK with forced tool-use.

    Returns the structured action dict, or None on any failure (SDK missing,
    no API key, network/timeout, malformed result) so the caller falls back
    to the keyword parser — same live-safety contract as the CLI path.

    Opt in with NEWTON_VLA_BACKEND=api (or backend="api"). Requires
    `pip install anthropic` and an ANTHROPIC_API_KEY; we deliberately require
    an explicit key rather than silently picking up an ambient profile, so
    the demo never makes a surprise billable call."""
    try:
        import anthropic
    except ImportError:
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    context = _format_history(history) + _format_world(world_state)
    try:
        client = anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=timeout)
        message = client.messages.create(
            model=_resolve_model_id(model or DEFAULT_MODEL),
            max_tokens=512,
            # The big, frozen prompt is marked cacheable; it engages once it
            # crosses the model's prompt-cache floor and is a no-op below it.
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=[_PARSE_TOOL],
            tool_choice={"type": "tool", "name": _PARSE_TOOL["name"]},
            messages=[{"role": "user", "content": f"{context}User: {user_input}"}],
        )
    except Exception:
        # Network errors, auth errors, bad model id, rate limits — all of it
        # collapses to "fall back to keywords" rather than crash the demo.
        return None
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == _PARSE_TOOL["name"]:
            data = block.input
            return data if isinstance(data, dict) else None
    return None


# Process-wide learned policy, injected by the demo when it wants the
# "learned" backend to use something other than the default mock policy
# (e.g. a real SmolVLA / zero-shot checkpoint). See `policy.py`.
_learned_policy: Any = None


def set_learned_policy(policy: Any) -> None:
    """Install the policy object used by the "learned" backend."""
    global _learned_policy
    _learned_policy = policy


def _call_learned_policy(
    user_input: str,
    world_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Parse via the configured learned intent policy (lazily importing the
    default mock policy). Returns None on any failure → keyword fallback."""
    policy = _learned_policy
    if policy is None:
        from .policy import get_default_policy
        policy = get_default_policy()
    try:
        return policy.parse(user_input, world_state=world_state)
    except Exception:
        return None


def _keyword_fallback(user_input: str) -> dict[str, Any]:
    """Deterministic keyword parser. Always returns a valid object.

    Typed text is trusted as-is — we do NOT run fuzzy_snap on it, because
    lowering the cutoff enough to fix mishears also snaps clean words to
    wrong ones (e.g. "left" → "pick"). Voice transcripts get pre-snapped
    by the voice module before they ever reach this parser.
    """
    text = user_input.lower()
    colors_in_order = [c for c in KNOWN_COLORS if c in text]
    # Pick up colors named in Chinese, preserving first-mention order.
    seen = set(colors_in_order)
    for zh, en in CHINESE_COLOR_MAP:
        if zh in text and en not in seen:
            colors_in_order.append(en)
            seen.add(en)

    # Gestures — decorative motions. Checked BEFORE pick/place/drive so the
    # word "wave" doesn't get mis-parsed as e.g. "drive". No color/target
    # needed; the `colors`-list field carries the gesture parameter
    # (`["audience"]` for "point at audience", `["3"]` for "dance 3 beats").
    if any(w in text for w in ("wave", "wav", "挥手", "挥挥手", "say hi", "招手")):
        return {
            "action": "wave",
            "color": None,
            "colors": None,
            "target": None,
            "reason": "keyword wave (decorative gesture)",
        }
    if any(w in text for w in ("point", "指", "指向", "指着")):
        direction = "left"
        if any(w in text for w in (" right", "右")):
            direction = "right"
        elif any(w in text for w in ("audience", "us", "camera", "观众", "镜头")):
            direction = "audience"
        return {
            "action": "point",
            "color": None,
            "colors": [direction],
            "target": None,
            "reason": f"keyword point {direction}",
        }
    if any(w in text for w in ("bow", "鞠躬", "敬礼")):
        return {
            "action": "bow",
            "color": None,
            "colors": None,
            "target": None,
            "reason": "keyword bow",
        }
    if any(w in text for w in ("dance", "跳舞", "舞")):
        return {
            "action": "dance",
            "color": None,
            "colors": None,
            "target": None,
            "reason": "keyword dance",
        }

    # Home — "go home", "drive home", "reset" etc. Check FIRST so "drive home"
    # doesn't get caught by the drive handler below.
    if any(w in text for w in ("home", "rest pose",
                                "回位", "归位", "回家", "回来", "复位", "归零")) \
       or text.strip() in {"reset", "recenter"}:
        return {
            "action": "home",
            "color": None,
            "colors": None,
            "target": None,
            "reason": "keyword home / reset",
        }

    # Stack / build a tower
    if any(w in text for w in ("stack", "tower", "build", "pile",
                                "塔", "堆", "叠", "搭建", "搭")):
        stack_colors = colors_in_order or ["red", "green", "blue"]
        return {
            "action": "stack",
            "color": None,
            "colors": stack_colors,
            "target": None,
            "reason": f"keyword stack of {stack_colors}",
        }

    # Pick
    if any(w in text for w in ("pick", "grab", "take", "lift", "get",
                                "拿", "抓", "取", "捡", "拾")):
        color = colors_in_order[0] if colors_in_order else None
        return {
            "action": "pick" if color else "unknown",
            "color": color,
            "colors": None,
            "target": None,
            "reason": f"keyword pick {color}" if color else "pick without color",
        }

    # Place — if the command mentions a color, we'll pick-AND-place.
    if any(w in text for w in ("place", "put", "drop", "set",
                                "放", "搁", "摆", "置")):
        target = None
        if any(w in text for w in (" left", "左")):
            target = (-0.6, 0.0)
        elif any(w in text for w in (" right", "右")):
            target = (0.9, 0.0)
        elif any(w in text for w in ("center", "middle", "中间")):
            target = (0.0, 0.0)
        else:
            m = re.search(r"([-+]?\d*\.?\d+)", text)
            if m:
                try:
                    x = float(m.group(1))
                    target = (max(-1.1, min(1.3, x)), 0.0)
                except ValueError:
                    pass
        color = colors_in_order[0] if colors_in_order else None
        return {
            "action": "place",
            "color": color,
            "colors": None,
            "target": target,
            "reason": f"place {color or 'held'} at {target}",
        }

    # Drive / move base — always returns an ABSOLUTE world x target.
    if any(w in text for w in ("drive", "move", "go", "roll", "travel",
                                "走", "移动", "开", "前进", "后退", "过去")):
        target_x: float | None = None
        if colors_in_order:
            color_x = {"red": 0.9, "green": 1.1, "blue": 1.3, "yellow": -0.9}
            target_x = color_x[colors_in_order[0]] * 0.8
            reason = f"drive near {colors_in_order[0]} block"
        else:
            m = re.search(r"([-+]?\d*\.?\d+)", text)
            if m:
                try:
                    val = float(m.group(1))
                    if any(w in text for w in (" left", " back", "reverse", "左", "后")):
                        val = -abs(val)
                    target_x = max(-1.6, min(1.6, val))
                    reason = f"drive to absolute x={target_x:+.2f}"
                except ValueError:
                    target_x = None
                    reason = "drive (could not parse distance)"
            elif any(w in text for w in (" left", " back", "reverse", "左", "后")):
                target_x = -0.7
                reason = "drive left"
            elif any(w in text for w in (" right", " forward", "ahead", "右", "前")):
                target_x = 0.7
                reason = "drive right"
            else:
                target_x = 0.0
                reason = "drive (no direction, defaulting to home)"
        return {
            "action": "drive",
            "color": None,
            "colors": None,
            "target": [target_x, 0.0],
            "reason": reason,
        }

    return {
        "action": "unknown",
        "color": None,
        "colors": None,
        "target": None,
        "reason": "no keywords matched",
    }


def parse_command(
    user_input: str,
    timeout: float = 20.0,
    history: list[tuple[str, dict[str, Any]]] | None = None,
    world_state: dict[str, Any] | None = None,
    backend: str | None = None,
    model: str | None = None,
) -> VLAResult:
    """Parse `user_input` to a VLAResult.

    Tries the selected language `backend` first, then falls back to the
    deterministic keyword matcher if anything goes wrong. Default 20s timeout
    fits a `claude --print` call with the full SYSTEM_PROMPT (empirically
    7-14s end-to-end for our short commands); shorten via the kwarg if a
    sub-2s guarantee matters more than getting the LLM-quality parse.

    `backend` selects the language model path ("cli" / "api" / "keyword" /
    "learned"); None uses NEWTON_VLA_BACKEND (default "cli"). `model`
    overrides the model alias/id for the cli and api backends. `history`
    (last few user/parse pairs) and `world_state` (block positions, held
    block, base_x) flow into the request so the model can resolve cross-turn
    and spatial references."""
    start = time.perf_counter()
    backend = backend or DEFAULT_BACKEND

    data: dict[str, Any] | None
    if backend == "keyword":
        data, source = None, "claude"
    elif backend == "api":
        data = _call_anthropic_api(user_input, timeout=timeout, history=history,
                                   world_state=world_state, model=model)
        source = "api"
    elif backend == "learned":
        data = _call_learned_policy(user_input, world_state=world_state)
        source = "learned"
    else:  # "cli" — the default; kept as the first call so test mocks of
        # `_call_claude_cli` continue to drive the whole pipeline.
        data = _call_claude_cli(user_input, timeout=timeout,
                                history=history, world_state=world_state, model=model)
        source = "claude"

    if data is None:
        data = _keyword_fallback(user_input)
        source = "fallback"

    # Sanitize fields.
    action = str(data.get("action", "unknown")).lower()
    if action not in {"pick", "place", "stack", "drive", "home",
                       "wave", "point", "bow", "dance", "unknown"}:
        action = "unknown"

    color = data.get("color")
    color = color.lower() if isinstance(color, str) and color.lower() in KNOWN_COLORS else None

    colors = data.get("colors") or []
    if isinstance(colors, list):
        if action == "point":
            # For gestures we let `colors` carry the direction string (left /
            # right / audience). Unknown values collapse to "left" downstream
            # in pipeline.build_plan_from.
            colors = [str(c).lower() for c in colors if isinstance(c, str)]
        else:
            colors = [c.lower() for c in colors
                      if isinstance(c, str) and c.lower() in KNOWN_COLORS]
    else:
        colors = []

    target_field = data.get("target")
    target: tuple[float, float] | None = None
    if isinstance(target_field, (list, tuple)) and len(target_field) >= 2:
        try:
            target = (float(target_field[0]), float(target_field[1]))
        except (TypeError, ValueError):
            target = None

    elapsed = (time.perf_counter() - start) * 1000
    return VLAResult(
        action=action,
        color=color,
        colors=colors or None,
        target=target,
        reason=str(data.get("reason", ""))[:200],
        source=source,
        latency_ms=elapsed,
    )
