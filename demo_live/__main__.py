"""Entry point for the Newton VLA Live Demo.

Run with:
    uv run python -m demo_live                  # windowed (debug)
    uv run python -m demo_live --fullscreen     # fullscreen (show time)
    uv run python -m demo_live --headless-probe # one frame + screenshot
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import threading
import time
from pathlib import Path

# Running as a top-level script needs the repo root on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import contextlib

import pygame

from demo_live import bootstrap, pipeline, scene, scene_legacy, scripted, sfx, telemetry
from demo_live import config as C
from demo_live import render as R
from demo_live.catcher import BallCatcher
from demo_live.collab import CollaborativeBuild
from demo_live.control import JointController
from demo_live.effects import EffectsLayer
from demo_live.physics import BLOCK_HALF, World, screen_to_world
from demo_live.tasks import TaskExecutor
from demo_live.vla import parse_command
from demo_live.voice import VoiceRecorder

# World-X anchor for the secondary FK-only arm. Far enough to the right
# that its workspace overlaps the original block field (red @ 0.7,
# green @ 1.1, blue @ 1.5) without colliding with the mobile base.
ARM_B_ANCHOR_X = 2.40


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument(
        "--industrial",
        action="store_true",
        help="Use the dual-arm industrial workstation renderer.",
    )
    p.add_argument(
        "--real-blocks",
        action="store_true",
        help="Simulate the colored blocks as real Newton rigid bodies (they "
        "stack, topple and collide) instead of the default teleport behavior.",
    )
    p.add_argument(
        "--collab",
        action="store_true",
        help="Industrial mode: replace Arm B's idle workpiece shuttle with a "
        "two-arm collaborative tower build (Arm A fetches, Arm B stacks) that "
        "runs while the stage is idle and yields the instant you press a key.",
    )
    p.add_argument("--width", type=int, default=C.WIDTH)
    p.add_argument("--height", type=int, default=C.HEIGHT)
    p.add_argument(
        "--headless-probe",
        action="store_true",
        help="Render one frame to PNG and exit (used for CI / smoke test).",
    )
    p.add_argument(
        "--probe-output",
        default="/tmp/demo_live_probe.png",
        help="Where to save the headless-probe PNG.",
    )
    p.add_argument(
        "--bench",
        type=float,
        default=0.0,
        help="Run for N seconds then exit, printing min/avg/max fps.",
    )
    p.add_argument(
        "--scripted",
        choices=["", "catch", "pick", "stack", "vla", "rehearsal"],
        default="",
        help="Auto-trigger a scenario for headless testing.",
    )
    p.add_argument(
        "--vla-command",
        default="stack a tower of red green and blue",
        help="Command string when --scripted vla is used.",
    )
    p.add_argument(
        "--screenshot-every",
        type=float,
        default=0.0,
        help="Save a PNG every N seconds (0 = off).",
    )
    p.add_argument(
        "--state-dump",
        default="",
        help="At exit, write world+catcher+executor terminal state as JSON to "
        "this path (used by end-to-end regression tests).",
    )
    p.add_argument(
        "--telemetry-off",
        action="store_true",
        help="Disable per-event CSV telemetry (which is on by default for "
        "live sessions). Automatically disabled for --headless-probe and "
        "--bench / --scripted runs since those don't need debrief data.",
    )
    p.add_argument(
        "--no-arm-b-idle",
        action="store_true",
        help="Disable the Arm B idle gesture loop. When --industrial is on "
        "and no rehearsal is running, Arm B otherwise cycles wave / point / "
        "bow / dance gestures whenever its executor goes idle so the "
        "workstation looks alive. Pass this to keep Arm B parked.",
    )
    return p.parse_args(argv)


def init_pygame(args: argparse.Namespace) -> tuple[pygame.Surface, pygame.Surface]:
    """Returns (internal_surface, window). Renderers draw to internal_surface
    at design-time resolution (1920×1080); we scale-blit to `window` each
    frame so the same hardcoded layout fits any user-chosen window size."""
    pygame.init()
    pygame.display.set_caption("Newton Embodied AI · Live Classroom Demo")
    flags = 0
    if args.fullscreen:
        flags = pygame.FULLSCREEN
    if args.headless_probe:
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    window = pygame.display.set_mode((args.width, args.height), flags)
    internal = pygame.Surface((C.WIDTH, C.HEIGHT))
    if not args.headless_probe:
        with contextlib.suppress(Exception):
            sfx.init()
    return internal, window


_scale_note_shown = False


def _present(surface: pygame.Surface, window: pygame.Surface) -> None:
    """Composite the design-time surface onto the actual window (scaling if
    sizes differ) and flip the display."""
    if window.get_size() == surface.get_size():
        window.blit(surface, (0, 0))
    else:
        # Full-frame smoothscale costs ~1-2 ms/frame (9-13 % of the 60 fps
        # budget). Fine, but worth one diagnostic line so a dropped-fps
        # report on an odd projector resolution is explainable.
        global _scale_note_shown
        if not _scale_note_shown:
            _scale_note_shown = True
            print(f"[display] window {window.get_size()} != internal "
                  f"{surface.get_size()} — per-frame smoothscale active (~1-2 ms)")
        pygame.transform.smoothscale(surface, window.get_size(), window)
    pygame.display.flip()


def main() -> None:
    args = parse_args()
    surface, window = init_pygame(args)
    clock = pygame.time.Clock()

    # Build physics world (takes a second while Warp loads cached kernels).
    # Factory so every reconstruction (R-reset, rehearsal reset, self-heal)
    # honors --real-blocks without repeating the flag at each call site.
    # NOTE: every reset path builds a *fresh* World, which discards all
    # real-block KINEMATIC/held state cleanly — so a reset mid-carry just drops
    # the block. If this is ever optimized to reuse a World across resets,
    # release every held block first or the grab flags will leak.
    def make_world() -> World:
        return World(real_blocks=args.real_blocks)

    world = make_world()
    controller = JointController(world)
    catcher = BallCatcher(world, controller)
    executor = TaskExecutor(world, controller, label="A")

    def _build_arm_b() -> bootstrap.ArmBBundle:
        # Closure over the *current* world + the immutable args.industrial
        # flag — every reset path (R key, rehearsal "reset:", self-heal)
        # creates a new World first and then calls this. Centralizing the
        # call keeps the four call sites identical.
        return bootstrap.make_arm_b(
            world,
            industrial=args.industrial,
            anchor_world_x=ARM_B_ANCHOR_X,
        )

    arm_b_rig, controller_b, executor_b, arm_b_gripper_state = _build_arm_b()
    # Arm B idle loop: when the secondary arm is enabled but no rehearsal
    # is driving it, cycle through `ARM_B_IDLE_CYCLE` so it never stands
    # frozen on its pedestal. Disabled with --no-arm-b-idle and during
    # any --scripted / --bench run (those own Arm B explicitly).
    arm_b_idle_enabled = (
        executor_b is not None
        and not args.no_arm_b_idle
        and not args.scripted
        and args.bench <= 0
        and not args.headless_probe
    )
    arm_b_idle_phase: int = 0
    arm_b_idle_next_at: float = 0.0   # time.perf_counter() set after prewarm
    prev_arm_b_busy: bool = False     # falling-edge detector for pause clock
    # Collaborative two-arm build (--collab). `None` when not running; created
    # lazily once the stage has been idle, torn down the instant the user acts.
    collab: CollaborativeBuild | None = None
    COLLAB_IDLE_DELAY = 3.0           # seconds of stage-idle before the arms start cooperating

    status: list[str] = ["Booted. Physics idle.", "Press 1/2/R/Q."]
    input_text = ""
    input_active = False
    mode_label = "IDLE"
    running = True
    fps = 0.0

    # Pre-warm: run a throw-away catcher cycle + a pick plan to compile and
    # cache all relevant Warp kernels and paths — first real user interaction
    # then responds instantly.
    status.append("Prewarming Warp kernels...")
    bootstrap.prewarm(world, controller, catcher, executor)
    status[-1] = "Prewarmed."
    status.append("Press 1/2/R/Q.")

    last_t = time.perf_counter()
    bench_start = last_t
    bench_samples: list[float] = []
    next_screenshot = last_t
    parse_thread: threading.Thread | None = None
    parse_result: dict = {"res": None, "cmd": ""}
    voice_recorder: VoiceRecorder | None = None
    # Mouse drag state for interactive catch throws
    drag_start_screen: tuple[int, int] | None = None
    drag_start_world: tuple[float, float] | None = None
    drag_cursor_world: tuple[float, float] | None = None
    DRAG_VELOCITY_SCALE = 4.0      # drag 1m on-screen → 4 m/s (good catchable range)
    # Rehearsal runner state (populated in the "elif rehearsal" branch below).
    rehearsal_queue: list[tuple[float, str]] = []
    rehearsal_next_at: float = last_t
    rehearsal_log: list[tuple[float, str]] = []
    # Original Claude CLI entry point, saved while an F5 rehearsal forces the
    # deterministic keyword fallback; restored by the "rehearsal:end" step.
    claude_cli_orig = None
    # Typing animation state (driven by `type:<text>` rehearsal steps).
    typing_target: str | None = None
    typing_progress: int = 0
    typing_next_char_at: float = 0.0
    TYPING_RATE = 25.0  # characters per second
    # Voice simulation state (driven by `voice:<raw>|<clean>` rehearsal steps).
    voice_sim_phase: str = ""
    voice_sim_until: float = 0.0
    voice_sim_raw: str = ""
    voice_sim_clean: str = ""
    # Conversational + scene context the VLA layer feeds to Claude. Lets the
    # LLM resolve cross-turn references ("do it again", "now green",
    # "stack them") and spatial references ("the leftmost block").
    parse_history: list[tuple[str, dict]] = []
    # Hybrid parse state: when a command fires, we run the keyword fallback
    # SYNCHRONOUSLY first to queue an immediate plan (~1ms), then fire
    # Claude in the background to confirm/refine. `parse_preflight_applied`
    # tells the drain block whether to skip queuing Claude's plan (it's
    # already executing the preflight one) or to apply it (preflight had
    # nothing to dispatch — e.g. unknown action).
    parse_preflight_applied: bool = False

    def _fire_parse(cmd: str) -> None:
        """Hybrid parse pipeline: keyword fallback now → Claude later.

        Synchronously runs `_keyword_fallback` (microseconds), queues the
        resulting plan on Arm A's executor immediately so the arm starts
        moving without waiting for the LLM. THEN starts a parse_thread
        with `parse_command` (Claude CLI, ~7-15s). When Claude returns,
        the drain block compares its result to the preflight: matching
        actions → silent confirm; differing actions → log only (the
        preflight plan is already executing).
        """
        nonlocal parse_thread, parse_preflight_applied, last_parsed_json
        nonlocal last_activity_t
        cmd = (cmd or "").strip()
        if not cmd:
            return
        # ---- preflight: keyword fallback (instant) ----
        from demo_live.vla import KNOWN_COLORS, _keyword_fallback
        pre_data = _keyword_fallback(cmd)
        pre_action = str(pre_data.get("action", "unknown")).lower()
        if pre_action not in {"pick", "place", "stack", "drive", "home",
                              "wave", "point", "bow", "dance", "unknown"}:
            pre_action = "unknown"
        pre_color = pre_data.get("color")
        pre_color = (
            pre_color.lower()
            if isinstance(pre_color, str) and pre_color.lower() in KNOWN_COLORS
            else None
        )
        pre_colors_raw = pre_data.get("colors") or []
        if isinstance(pre_colors_raw, list):
            if pre_action == "point":
                # For "point", `colors` carries the direction (left / right /
                # audience), NOT a color name — pass through unfiltered.
                pre_colors = [str(c).lower() for c in pre_colors_raw
                              if isinstance(c, str)]
            else:
                pre_colors = [c.lower() for c in pre_colors_raw
                              if isinstance(c, str) and c.lower() in KNOWN_COLORS]
        else:
            pre_colors = []
        pre_target = None
        pt = pre_data.get("target")
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            try:
                pre_target = (float(pt[0]), float(pt[1]))
            except (TypeError, ValueError):
                pre_target = None

        plan = pipeline.build_plan_from(
            executor, controller, world,
            pre_action, pre_color, pre_colors or None, pre_target,
        )
        triggered_home = (pre_action == "home")
        if plan or triggered_home:
            if plan:
                executor.queue(plan)
            parse_preflight_applied = True
            status.append(f'  ⚡ keyword preflight: {pre_action}'
                          + (f' {pre_color}' if pre_color else '')
                          + (f' {pre_colors}' if pre_colors else '')
                          + '  (Claude refining…)')
            last_parsed_json = {
                "user": cmd,
                "via": "preflight (kw)",
                "action": pre_action,
                "color": pre_color,
                "colors": pre_colors or None,
                "target": list(pre_target) if pre_target else None,
                "reason": "keyword preflight",
            }
            if args.scripted or args.bench:
                print(f"[preflight] action={pre_action} color={pre_color} "
                      f"colors={pre_colors} target={pre_target}")
            # Telemetry: log the preflight dispatch separately from the
            # eventual Claude-confirmed VLA event. This explains the
            # debrief story "arm moved at T+0.001s but Claude returned at
            # T+9.4s" — without this hook, the CSV only shows the slow
            # Claude row and the audience reaction looks unexplained.
            if tele:
                tele.event(
                    "preflight",
                    user_input=cmd,
                    parsed_action=pre_action,
                    backend="keyword",
                    success=True,
                    detail=(pre_color or "")
                           + (f" / {pre_colors}" if pre_colors else "")
                           + (f" @ {pre_target}" if pre_target else ""),
                )
        else:
            parse_preflight_applied = False
            status.append('  ⏳ no preflight match — waiting for Claude…')
            if tele:
                tele.event(
                    "preflight",
                    user_input=cmd,
                    parsed_action=pre_action,
                    backend="keyword",
                    success=False,
                    detail="no match — waiting for Claude",
                )
        last_activity_t = time.perf_counter()

        # ---- background Claude (slow, may confirm or refine) ----
        # Generation counter prevents a slow stale worker from clobbering a
        # fresh one's result. The latest call bumps `gen`; each worker
        # captures its own gen at start and only writes if it still matches
        # the live one when it finishes. Stale workers write nothing.
        parse_result["res"] = None
        parse_result["cmd"] = cmd
        parse_result["gen"] = parse_result.get("gen", 0) + 1
        my_gen = parse_result["gen"]

        def _worker(c: str = cmd, gen: int = my_gen) -> None:
            res = parse_command(
                c, history=list(parse_history),
                world_state=pipeline.world_snapshot(world, executor))
            # Only the most recent worker is allowed to publish its result;
            # any older worker that finished after this one is dropped.
            if parse_result.get("gen") == gen:
                parse_result["res"] = res

        parse_thread = threading.Thread(target=_worker, daemon=True)
        parse_thread.start()
    # Telemetry: per-event CSV for post-class debrief. Disabled for
    # headless-probe / bench / scripted runs (no audience, no debrief).
    telemetry_enabled = (
        not args.telemetry_off
        and not args.headless_probe
        and args.bench <= 0
        and not args.scripted
    )
    tele: telemetry.TelemetryLogger | None = (
        telemetry.TelemetryLogger(path=telemetry.default_path())
        if telemetry_enabled else None
    )

    # Presenter features
    effects = EffectsLayer()
    command_history: list[str] = []        # last few user commands (typed/spoken)
    last_parsed_json: dict | None = None   # for the "AI thinking" panel
    last_activity_t: float = last_t        # for idle auto-home
    IDLE_HOME_SECONDS = 6.0
    # Track catch/stack state transitions to trigger SFX + FX exactly once.
    prev_catch_count = catcher.catch_count
    prev_executor_busy = executor.busy
    prev_catcher_committed = False    # rising edge → "arm locked on" effect
    # Slow-motion dramatic beat: 1.5 s of 0.33× dt after a catch or after a
    # multi-step program (e.g. stack) finishes. Disabled in --scripted /
    # --bench / --headless-probe because they must run at real-time.
    SLOWMO_DURATION_S = 1.5
    SLOWMO_FACTOR = 0.33
    slowmo_enabled = (
        not args.scripted and args.bench <= 0 and not args.headless_probe
    )
    slowmo_until: float = 0.0

    # Auto-trigger scripted scenarios.
    if args.scripted == "catch":
        catcher.start(manual=False)
        mode_label = "BALL  CATCH"
        status.append("Scripted ball-catch start.")
    elif args.scripted == "pick":
        executor.queue(executor.make_pick("red") + executor.make_place((-0.6, 0.0)))
        mode_label = "TASK  EXEC"
        status.append("Scripted pick-and-place (red → left).")
    elif args.scripted == "stack":
        executor.queue(executor.make_stack(["red", "green", "blue"]))
        mode_label = "TASK  EXEC"
        status.append("Scripted stack (red, green, blue).")
    elif args.scripted == "vla":
        mode_label = "TALK TO ARM"
        status.append(f'Scripted VLA command: {args.vla_command!r}')
        _fire_parse(args.vla_command)
    elif args.scripted == "rehearsal":
        # Claude CLI is invoked for real (with the keyword fallback inside
        # parse_command catching any CLI hiccups). The script lives in
        # `demo_live.scripted` so it can be edited without touching the loop.
        mode_label = "REHEARSAL"
        status.append("Rehearsal starting — Claude CLI parses each command.")
        rehearsal_queue = scripted.build_default_rehearsal(industrial=args.industrial)

    # Track consecutive frame-level failures so we can bail out on truly
    # broken states (e.g. OOM) instead of spinning infinitely.
    frame_errors = 0

    while running:
      try:
        # --- events --------------------------------------------------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 \
                    and catcher.state != BallCatcher.STATE_IDLE and catcher.manual:
                # Only let clicks inside the main viewport (not the side panel) begin a throw.
                mx, my = event.pos
                if mx < C.VIEWPORT_WIDTH and my < C.HEIGHT - C.FOOTER_HEIGHT:
                    drag_start_screen = (mx, my)
                    drag_start_world = screen_to_world(mx, my)
                    drag_cursor_world = drag_start_world
            elif event.type == pygame.MOUSEMOTION and drag_start_screen is not None:
                drag_cursor_world = screen_to_world(*event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 \
                    and drag_start_screen is not None:
                end_world = screen_to_world(*event.pos)
                sx, sz = drag_start_world
                ex, ez = end_world
                # Slingshot: velocity is drag × scale, in the OPPOSITE direction
                # of the drag (pull back to aim).
                vx = (sx - ex) * DRAG_VELOCITY_SCALE
                vz = (sz - ez) * DRAG_VELOCITY_SCALE
                # Minimum throw speed so tiny wiggles don't count.
                if math.hypot(vx, vz) > 1.0:
                    catcher.external_launch((sx, sz), (vx, vz))
                    status.append(
                        f"Throw from ({sx:+.2f}, {sz:+.2f})  "
                        f"v=({vx:+.1f}, {vz:+.1f}) m/s"
                    )
                drag_start_screen = None
                drag_start_world = None
                drag_cursor_world = None
            elif event.type == pygame.KEYDOWN:
                # When the user is typing, hijack ALL key handling to the input
                # branch so mode/quit keys can't eat characters.
                if input_active and event.key not in (pygame.K_ESCAPE, pygame.K_RETURN):
                    if event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.key == pygame.K_SPACE:
                        input_text += " "
                    elif event.unicode and event.unicode.isprintable() and event.unicode != " ":
                        input_text += event.unicode
                    elif (event.mod & pygame.KMOD_META) and event.key == pygame.K_q:
                        running = False
                    continue

                if event.key == pygame.K_q and (event.mod & pygame.KMOD_META or not input_active):
                    running = False
                elif event.key == pygame.K_ESCAPE:
                    if input_active:
                        input_active = False
                        input_text = ""
                        mode_label = "IDLE"
                    else:
                        running = False
                elif event.key == pygame.K_RETURN and input_active:
                    cmd = input_text.strip()
                    if cmd:
                        if parse_thread is not None and parse_thread.is_alive():
                            status.append("  (superseding previous command)")
                        status.append(f'> "{cmd}"')
                        command_history.append(cmd)
                        command_history[:] = command_history[-5:]
                        _fire_parse(cmd)
                        sfx.play("click")
                    input_text = ""
                    input_active = False
                elif event.key == pygame.K_1 and not input_active:
                    mode_label = "BALL  CATCH"
                    catcher.start(manual=True)
                    status.append("Ball-catch — click & drag anywhere to throw.")
                    effects.banner("BALL  CATCH", color=C.PRIMARY)
                    sfx.play("mode")
                    last_activity_t = time.perf_counter()
                    if tele:
                        tele.event("mode", detail="ball_catch")
                elif event.key == pygame.K_2 and not input_active:
                    mode_label = "TALK TO ARM"
                    input_active = True
                    input_text = ""
                    status.append("VLA mode active. Type a command.")
                    effects.banner("TYPE  A  COMMAND", color=C.PRIMARY)
                    sfx.play("mode")
                    last_activity_t = time.perf_counter()
                    if tele:
                        tele.event("mode", detail="talk_to_arm")
                elif event.key == pygame.K_3 and not input_active:
                    # Toggle semantics: first press starts recording,
                    # second press stops and kicks off transcription.
                    if voice_recorder is None:
                        voice_recorder = VoiceRecorder(max_duration=10.0)
                        voice_recorder.start()
                        if voice_recorder.result is not None and not voice_recorder.result.ok:
                            status.append(f"  (mic failed: {voice_recorder.result.error})")
                            voice_recorder = None
                        else:
                            mode_label = "LISTENING"
                            status.append("Listening…  press 3 again to stop.")
                            effects.banner("LISTENING", color=C.ACCENT)
                            sfx.play("mode")
                    elif voice_recorder.recording:
                        voice_recorder.stop()
                        mode_label = "TRANSCRIBING"
                        status.append(f"  stopped at {voice_recorder.elapsed():.1f}s  transcribing…")
                        sfx.play("click")
                    last_activity_t = time.perf_counter()
                elif event.key == pygame.K_F5 and not input_active:
                    # One-key rehearsal — useful right before going on stage
                    # to confirm everything is warm and to demo without typing.
                    # Claude is swapped out for the deterministic keyword
                    # fallback for the duration (so the warm-up never stalls
                    # on a slow LLM) and restored by the "rehearsal:end" step.
                    status.append("F5 → auto-rehearsal sequence (~55 s)")
                    import demo_live.vla as _vla_mod
                    if claude_cli_orig is None:
                        claude_cli_orig = _vla_mod._call_claude_cli
                    _vla_mod._call_claude_cli = lambda *a, **k: None
                    rehearsal_queue = list(scripted.REHEARSAL_SCRIPT_F5)
                    rehearsal_queue.append((0.5, "rehearsal:end"))
                    rehearsal_next_at = time.perf_counter()
                    mode_label = "REHEARSAL"
                    effects.banner("REHEARSAL", color=C.ACCENT)
                    sfx.play("mode")
                elif event.key == pygame.K_r and not input_active:
                    world = make_world()
                    controller = JointController(world)
                    catcher = BallCatcher(world, controller)
                    executor = TaskExecutor(world, controller)
                    arm_b_rig, controller_b, executor_b, arm_b_gripper_state = _build_arm_b()
                    collab = None  # stale executors after reset — restart collab fresh next idle
                    for _ in range(10):
                        world.step()
                    mode_label = "IDLE"
                    status.append("Scene reset.")
                    effects.banner("RESET", color=C.INK_SOFT)
                    sfx.play("click")
                    last_activity_t = time.perf_counter()

        # --- rehearsal step engine ---------------------------------
        # Drains the queue built either by `--scripted rehearsal` at startup
        # or by the F5 key during a live session (the queue is only ever
        # populated by those two paths).
        if rehearsal_queue and time.perf_counter() >= rehearsal_next_at:
            delay, step = rehearsal_queue.pop(0)
            t_elapsed = time.perf_counter() - bench_start
            rehearsal_log.append((t_elapsed, step))
            print(f"[rehearsal  {t_elapsed:5.1f}s]  {step}")
            if step == "catch:start":
                catcher.start(manual=False)
                mode_label = "BALL  CATCH"
            elif step == "catch:stop":
                catcher.stop()
                mode_label = "IDLE"
            elif step == "reset":
                world = make_world()
                controller = JointController(world)
                catcher = BallCatcher(world, controller)
                executor = TaskExecutor(world, controller)
                arm_b_rig, controller_b, executor_b, arm_b_gripper_state = _build_arm_b()
                collab = None  # stale executors after reset — restart collab fresh next idle
                for _ in range(10):
                    world.step()
                mode_label = "IDLE"
            elif step.startswith("vla:"):
                cmd_text = step[4:]
                _fire_parse(cmd_text)
                mode_label = "TALK TO ARM"
            elif step.startswith("type:"):
                # Simulated typed input — typing animator (below) advances
                # input_text one char per frame, then fires parse on completion.
                typing_target = step[5:]
                typing_progress = 0
                typing_next_char_at = time.perf_counter() + 0.4
                input_active = True
                input_text = ""
                last_parsed_json = None
                mode_label = "TALK TO ARM"
                effects.banner("TYPING…", color=C.PRIMARY, duration=0.6)
                sfx.play("mode")
            elif step.startswith("arm_b:"):
                # Direct dispatch to Arm B via the deterministic keyword
                # parser — no LLM call, so it can fire in parallel with
                # an in-flight Arm A LLM parse without contention.
                cmd_text = step[6:]
                if executor_b is None or controller_b is None:
                    status.append(f"  [Arm B skipped] {cmd_text!r}")
                    rehearsal_next_at = time.perf_counter() + delay
                    continue
                from demo_live.vla import _keyword_fallback
                data = _keyword_fallback(cmd_text)
                action_b = str(data.get("action") or "unknown").lower()
                color_b = data.get("color")
                colors_b = data.get("colors")
                target_b = data.get("target")
                if isinstance(target_b, (list, tuple)) and len(target_b) >= 2:
                    target_b = (float(target_b[0]), float(target_b[1]))
                else:
                    target_b = None
                # Reuse the single source of truth for action → plan. This
                # automatically picks up new actions (wave/point/bow/dance,
                # drive, etc.) without divergence between Arm A and Arm B.
                plan_b = pipeline.build_plan_from(
                    executor_b, controller_b, world,
                    action_b, color_b, colors_b, target_b,
                )
                if plan_b:
                    executor_b.queue(plan_b)
                status.append(f'  [Arm B] {cmd_text!r} → {action_b}')
                if args.scripted or args.bench:
                    print(f"[arm_b] {cmd_text!r} → action={action_b} "
                          f"color={color_b} colors={colors_b}")
            elif step.startswith("voice:"):
                # Simulated voice input. Format: "voice:<noisy raw>|<clean>".
                # The noisy half mimics ASR output; fuzzy_snap (already
                # integrated upstream of parse) would normally produce the
                # clean half. We display both for the audience, then fire
                # parse on the clean transcript.
                payload = step[6:]
                parts = payload.split("|", 1)
                voice_sim_raw = parts[0]
                voice_sim_clean = parts[1] if len(parts) > 1 else parts[0]
                voice_sim_phase = "listening"
                voice_sim_until = time.perf_counter() + 1.5
                input_active = False
                mode_label = "LISTENING"
                effects.banner("LISTENING", color=C.ACCENT, duration=0.8)
                sfx.play("mode")
                # Speak the clean command via macOS TTS so the audience
                # hears the input alongside the visual LISTENING banner.
                # Non-blocking; failures (e.g. `say` not on PATH) fall
                # through silently.
                with contextlib.suppress(FileNotFoundError, OSError):
                    subprocess.Popen(
                        ["say", "-v", "Samantha", voice_sim_clean],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            elif step == "rehearsal:end":
                # F5 warm-up done — hand the stage back: restore the real
                # Claude CLI (it was swapped for the keyword fallback so the
                # rehearsal never stalls on a slow LLM) and return to IDLE.
                if claude_cli_orig is not None:
                    import demo_live.vla as _vla_mod
                    _vla_mod._call_claude_cli = claude_cli_orig
                    claude_cli_orig = None
                mode_label = "IDLE"
                status.append("Rehearsal done — Claude re-enabled. Press 1/2/R/Q.")
                effects.banner("READY", color=C.PRIMARY)
                last_activity_t = time.perf_counter()
            # "wait" is a no-op; delay advances the clock.
            rehearsal_next_at = time.perf_counter() + delay
            if not rehearsal_queue and args.scripted == "rehearsal":
                # Drain done — append one final "wait" so the closing beat
                # has room to settle on-screen, then let the bench timeout
                # (or the user) end the run. (F5 rehearsals instead end with
                # an explicit "rehearsal:end" step and leave the queue empty.)
                rehearsal_queue = [(5.0, "wait")]

        # --- typing animator (rehearsal `type:` steps) -------------
        if typing_target is not None and time.perf_counter() >= typing_next_char_at:
            if typing_progress < len(typing_target):
                input_text = typing_target[:typing_progress + 1]
                typing_progress += 1
                typing_next_char_at = time.perf_counter() + 1.0 / TYPING_RATE
            else:
                cmd = input_text.strip()
                if cmd:
                    status.append(f'> "{cmd}"')
                    command_history.append(cmd)
                    command_history[:] = command_history[-5:]
                    _fire_parse(cmd)
                    sfx.play("click")
                input_text = ""
                input_active = False
                typing_target = None
                typing_progress = 0

        # --- voice simulator (rehearsal `voice:` steps) ------------
        if voice_sim_phase == "listening" and time.perf_counter() >= voice_sim_until:
            voice_sim_phase = "transcribing"
            mode_label = "TRANSCRIBING"
            voice_sim_until = time.perf_counter() + 0.7
        elif voice_sim_phase == "transcribing" and time.perf_counter() >= voice_sim_until:
            voice_sim_phase = ""
            if voice_sim_raw and voice_sim_raw != voice_sim_clean:
                status.append(f'  🎤 heard: "{voice_sim_raw}"')
                status.append(f'  ↳ snapped: "{voice_sim_clean}"  [simulated]')
            else:
                status.append(f'  🎤 "{voice_sim_clean}"  [simulated]')
            command_history.append(voice_sim_clean)
            command_history[:] = command_history[-5:]
            sfx.play("ding")
            if parse_thread is not None and parse_thread.is_alive():
                status.append("  (superseding previous command)")
            status.append(f'> "{voice_sim_clean}"')
            _fire_parse(voice_sim_clean)
            mode_label = "TALK TO ARM"

        # --- drain voice recorder (toggle flow) --------------------
        if voice_recorder is not None and not voice_recorder.is_busy and voice_recorder.result is not None:
            v = voice_recorder.result
            voice_recorder = None
            if v is None or not v.ok:
                err = v.error if v else "unknown"
                if tele:
                    tele.event("voice", success=False, backend="voice", detail=err)
                status.append(f"  (mic failed: {err})")
                # Surface the failure so the audience sees what happened —
                # otherwise the input box just silently stays empty after
                # "LISTENING" disappears, which reads as "the demo is broken".
                effects.banner(
                    f"VOICE FAILED — {err[:48]} — type instead",
                    color=C.LED_AMBER,
                    duration=1.6,
                )
                mode_label = "IDLE"
                sfx.play("miss")
            else:
                if v.raw_transcript and v.raw_transcript != v.transcript:
                    status.append(f'  🎤 heard: "{v.raw_transcript}"')
                    status.append(f'  ↳ snapped: "{v.transcript}"  [{v.latency_ms:.0f}ms]')
                else:
                    status.append(f'  🎤 "{v.transcript}"  [{v.language_used}, {v.latency_ms:.0f}ms]')
                command_history.append(v.transcript)
                command_history[:] = command_history[-5:]
                sfx.play("ding")
                if tele:
                    tele.event("voice", success=True, backend="voice",
                               user_input=v.transcript,
                               latency_ms=v.latency_ms,
                               detail=v.language_used)
                if parse_thread is not None and parse_thread.is_alive():
                    status.append("  (superseding previous command)")
                status.append(f'> "{v.transcript}"')
                _fire_parse(v.transcript)
                mode_label = "TALK TO ARM"

        # --- drain parse thread ------------------------------------
        if parse_thread is not None and not parse_thread.is_alive():
            res = parse_result["res"]
            parse_thread = None
            if res is None:
                status.append("  (Claude crashed; preflight stands)"
                              if parse_preflight_applied else "  (parser crashed)")
                sfx.play("miss")
            else:
                if tele:
                    tele.event(
                        "vla",
                        user_input=parse_result.get("cmd", ""),
                        parsed_action=res.action,
                        latency_ms=res.latency_ms,
                        backend=res.source,
                        success=res.action != "unknown",
                        detail=(res.color or "")
                               + (f" / {res.colors}" if res.colors else "")
                               + (f" @ {res.target}" if res.target else ""),
                    )
                if args.scripted or args.bench:
                    print(f"[parse] source={res.source} {res.latency_ms:.0f}ms · "
                          f"action={res.action} color={res.color} "
                          f"colors={res.colors} target={res.target} · "
                          f"reason={res.reason}")
                # Record this turn for future multi-turn references.
                parse_history.append((parse_result.get("cmd", ""), {
                    "action": res.action,
                    "color": res.color,
                    "colors": res.colors,
                    "target": list(res.target) if res.target else None,
                }))
                parse_history[:] = parse_history[-5:]

                if parse_preflight_applied:
                    # Preflight already moved the arm. Compare; log only.
                    pre = last_parsed_json or {}
                    pre_color = pre.get("color")
                    pre_action = pre.get("action")
                    same = (res.action == pre_action and res.color == pre_color)
                    # When `res.source == "fallback"` Claude was unavailable
                    # and the keyword parser stood in. Surface that to the
                    # audience so the "AI" label stays honest.
                    via = "↓ keyword fallback" if res.source == "fallback" else "via Claude"
                    if same:
                        status.append(f"  ✓ {via} confirmed "
                                      f"({res.latency_ms:.0f}ms) · {res.reason}")
                    else:
                        status.append(
                            f"  ⚠ {via} differs ({res.latency_ms:.0f}ms): "
                            f"{res.action}/{res.color} — preflight already "
                            f"executing {pre_action}/{pre_color}")
                    # Refresh AI-thinking panel with Claude's richer reason
                    # (keep the executed action — that's the preflight one).
                    last_parsed_json = {
                        "user": pre.get("user", parse_result.get("cmd", "")),
                        "via": f"{res.source}  {res.latency_ms:.0f}ms",
                        "action": pre_action,
                        "color": pre_color,
                        "colors": pre.get("colors"),
                        "target": pre.get("target"),
                        "reason": res.reason,
                    }
                else:
                    # No preflight (e.g. unknown / non-actionable command);
                    # apply Claude's plan now as the legacy path.
                    status.append(f"  ← {res.source} {res.latency_ms:.0f}ms · "
                                  f"{res.reason}")
                    last_parsed_json = {
                        "user": parse_result.get("cmd", ""),
                        "via": f"{res.source}  {res.latency_ms:.0f}ms",
                        "action": res.action,
                        "color": res.color,
                        "colors": res.colors,
                        "target": (list(res.target) if res.target else None),
                        "reason": res.reason,
                    }
                    plan = pipeline.build_plan_from(
                        executor, controller, world,
                        res.action, res.color, res.colors,
                        res.target if res.target else None,
                    )
                    if plan:
                        executor.queue(plan)
                    elif res.action == "unknown":
                        status.append("  (try: pick red / stack / home)")
                        effects.banner(
                            "DIDN'T CATCH THAT — TRY: pick red · stack · home",
                            color=C.LED_AMBER,
                            duration=1.6,
                        )
                        sfx.play("miss")
            parse_preflight_applied = False
            mode_label = "IDLE"

        # --- control + physics --------------------------------------
        # Slow-motion stretches the dramatic beat right after a catch / tower
        # finish. We scale only the dt that feeds the simulation; the actual
        # frame cadence (clock.tick at the end) stays at 60 fps so the UI
        # stays smooth.
        in_slowmo = slowmo_enabled and time.perf_counter() < slowmo_until
        frame_dt = (1.0 / C.FPS) * (SLOWMO_FACTOR if in_slowmo else 1.0)
        if catcher.state != BallCatcher.STATE_IDLE:
            msg = catcher.update(frame_dt)
            if msg and (not status or status[-1] != msg):
                status.append(msg)
                if args.scripted or args.bench:
                    print(f"[catcher] {msg}")
        prev_exec_status = executor.status_text
        executor.update(frame_dt)
        if executor_b is not None and controller_b is not None:
            executor_b.update(frame_dt)
            controller_b.update(frame_dt)

        # Collaborative two-arm build (--collab): while the stage is idle the
        # two arms build a tower together (Arm A fetches → handoff → Arm B
        # stacks), looping build/teardown. It commandeers Arm A, so it must
        # yield the instant the user does anything — pressing a key, talking,
        # or a parse in flight all tear it down and free both arms.
        if args.collab and arm_b_idle_enabled and executor_b is not None and controller_b is not None:
            user_busy = (
                catcher.state != BallCatcher.STATE_IDLE
                or input_active
                or bool(parse_thread and parse_thread.is_alive())
                or bool(voice_recorder and voice_recorder.is_busy)
            )
            if user_busy:
                if collab is not None:
                    # Release any held real blocks before dropping the plans so
                    # nothing is left stuck KINEMATIC, then hand both arms back.
                    # In teleport mode gravity won't settle an interrupted
                    # carry, so drop the block straight to the ground at its
                    # current x instead of leaving it floating mid-air.
                    for exe in (executor, executor_b):
                        if exe.held is not None:
                            world.release_block(exe.held)
                            if not world.real_blocks:
                                world.move_block(
                                    exe.held, (exe.held.xz[0], BLOCK_HALF)
                                )
                        exe.clear()
                    collab = None
            else:
                if collab is None and time.perf_counter() - last_activity_t > COLLAB_IDLE_DELAY:
                    collab = CollaborativeBuild(world, executor, executor_b)
                if collab is not None:
                    collab.update()
        # Arm B idle gesture loop. When the secondary arm has nothing else
        # to do, cycle through `ARM_B_IDLE_CYCLE` so it never just stands
        # frozen on its pedestal. Disabled with --no-arm-b-idle and during
        # any --scripted / --bench run (the rehearsal explicitly drives
        # Arm B via `arm_b:` steps and the two would fight).
        elif arm_b_idle_enabled and executor_b is not None and controller_b is not None:
            busy_now = executor_b.busy
            # Falling edge: a gesture just finished → start the pause clock.
            if prev_arm_b_busy and not busy_now:
                arm_b_idle_next_at = time.perf_counter() + scripted.ARM_B_IDLE_PAUSE_S
            if not busy_now and time.perf_counter() >= arm_b_idle_next_at:
                step = scripted.ARM_B_IDLE_CYCLE[arm_b_idle_phase]
                plan_b_idle = pipeline.build_plan_from(
                    executor_b, controller_b, world,
                    step.action, step.color, step.colors, step.target,
                )
                if plan_b_idle:
                    executor_b.queue(plan_b_idle)
                arm_b_idle_phase = (arm_b_idle_phase + 1) % len(scripted.ARM_B_IDLE_CYCLE)
                # Prevent re-firing on the same frame; the falling edge above
                # will set a real deadline once the next step completes.
                arm_b_idle_next_at = float("inf")
            prev_arm_b_busy = busy_now
        if executor.status_text and executor.status_text != prev_exec_status:
            status.append(executor.status_text)
            if args.scripted or args.bench:
                print(f"[exec] {executor.status_text}")
            # Per-waypoint SFX: subtle click when arm transitions waypoints.
            if "Released" in executor.status_text:
                sfx.play("thud")
            elif "Picked up" in executor.status_text:
                sfx.play("click")
        controller.update(frame_dt)
        world.integrate_ball(frame_dt)
        world.integrate_base(frame_dt)
        world.step()

        # Sample end-effector for the motion trail (only while busy, so a
        # resting arm doesn't draw a stationary blob).
        if executor.busy or catcher.state != BallCatcher.STATE_IDLE:
            arm = world.arm_state_from_target()
            ee_x, ee_z = arm.end_effector
            ee_screen_x = C.ORIGIN_X_PX + int((ee_x + world.base_x) * C.PX_PER_M)
            ee_screen_y = C.GROUND_Y_PX - int(ee_z * C.PX_PER_M)
            effects.push_trail((ee_screen_x, ee_screen_y))

        # Highlight the "commit" decision moment — the frame the catcher
        # solves IK and locks the arm onto an intercept point. Reads as a
        # split-second "the robot just decided" beat for the audience.
        is_committed = catcher.committed_target is not None
        if is_committed and not prev_catcher_committed:
            arm = world.arm_state_from_target()
            ee = arm.end_effector
            cx = C.ORIGIN_X_PX + int((ee[0] + world.base_x) * C.PX_PER_M)
            cy = C.GROUND_Y_PX - int(ee[1] * C.PX_PER_M)
            effects.ring((cx, cy), color=C.LED_AMBER, duration=0.4, max_radius=110.0)
            sfx.play("click")
        prev_catcher_committed = is_committed

        # Celebrate catches on the rising edge of catch_count.
        if catcher.catch_count > prev_catch_count:
            if tele:
                tele.event("catch", success=True,
                           detail=f"{catcher.catch_count}/{catcher.attempt_count}")
            arm = world.arm_state_from_target()
            ee = arm.end_effector
            sx, sy = C.ORIGIN_X_PX + int((ee[0] + world.base_x) * C.PX_PER_M), \
                     C.GROUND_Y_PX - int(ee[1] * C.PX_PER_M)
            effects.burst((sx, sy), color=C.ACCENT, count=32)
            effects.banner(f"CAUGHT  ·  {catcher.catch_count}", color=C.ACCENT, duration=0.7)
            sfx.play("pop")
            last_activity_t = time.perf_counter()
            # Only enter slow-mo when the executor is idle — otherwise an
            # in-flight pick/place segment (which tracks time via
            # perf_counter, not dt) keeps moving at real-time while the
            # physics dt drops to 0.33×, and the arm visibly "skates" past
            # its waypoints. Gating on !busy makes the visual coherent.
            if slowmo_enabled and not executor.busy:
                slowmo_until = time.perf_counter() + SLOWMO_DURATION_S
                effects.banner("· slow-mo ·", color=C.ACCENT,
                               duration=SLOWMO_DURATION_S, y_band=1)
        prev_catch_count = catcher.catch_count

        # Celebrate when a multi-step program finishes (falling edge of busy).
        if prev_executor_busy and not executor.busy:
            # Success splash at the tower location.
            effects.banner("DONE!", color=C.GREEN, duration=0.8)
            sfx.play("success")
            # Falling edge of busy means the executor JUST became idle,
            # so the "executor coherent under slow-mo" precondition holds.
            if slowmo_enabled:
                slowmo_until = time.perf_counter() + SLOWMO_DURATION_S
                effects.banner("· slow-mo ·", color=C.GREEN,
                               duration=SLOWMO_DURATION_S, y_band=1)
        prev_executor_busy = executor.busy

        # Block out-of-bounds auto-recovery: if a block ever ends up way off
        # screen (rare, but can happen if physics coincidentally flings one),
        # teleport it back to its starting slot. Held blocks are skipped —
        # see World.recover_out_of_bounds.
        world.recover_out_of_bounds()

        # Only the last 6 status lines are ever rendered; cap the backlog so
        # an hours-long booth session can't grow it without bound.
        if len(status) > 240:
            del status[:-60]

        # Idle auto-home: after IDLE_HOME_SECONDS of no activity, gently
        # return to rest pose + base to 0. Clears the stage between segments.
        idle = time.perf_counter() - last_activity_t
        if (
            idle > IDLE_HOME_SECONDS
            and catcher.state == BallCatcher.STATE_IDLE
            and not executor.busy
            and not (parse_thread and parse_thread.is_alive())
            and not (voice_recorder and voice_recorder.is_busy)
            and mode_label != "IDLE"
        ):
            controller.go_home()
            world.drive_to(0.0)
            mode_label = "IDLE"
            # Don't spam the banner; just reset the timer so it doesn't retrigger.
            last_activity_t = time.perf_counter()

        # --- render --------------------------------------------------
        R.paper_background(surface)
        # Main viewport chrome
        render_scene = scene if args.industrial else scene_legacy
        render_scene.draw_ground(surface)
        # Thinking indicator: parse_thread alive OR voice in transcription.
        ai_thinking_now = (
            (parse_thread is not None and parse_thread.is_alive())
            or voice_sim_phase in ("listening", "transcribing")
        )
        if args.industrial:
            scene.draw_arm_base(surface, world,
                                mode_label=mode_label, thinking=ai_thinking_now)
            scene.draw_arm_pedestal(surface, ARM_B_ANCHOR_X)
        else:
            scene_legacy.draw_arm_base(surface, world)
        # Halo the block the robot currently "intends to act on" — single
        # color from the latest parse, while the executor is busy and the
        # block isn't already in hand.
        focus_color = None
        if last_parsed_json and executor.busy:
            cand = last_parsed_json.get("color")
            held_color = getattr(executor.held, "color", None) if executor.held else None
            if isinstance(cand, str) and cand != held_color:
                focus_color = cand
        if args.industrial:
            scene.draw_blocks(surface, world, target_color=focus_color)
        else:
            scene_legacy.draw_blocks(surface, world)
        if catcher.state != BallCatcher.STATE_IDLE:
            scene.draw_trajectory(surface, world)
            pred = catcher.last_prediction
            intercept = pred.intercept_xz if pred and pred.ok else None
            scene.draw_intercept_marker(surface, intercept)
            scene.draw_ball(surface, world)
        # Launch preview arrow while the user is aiming a manual throw.
        if drag_start_world is not None and drag_cursor_world is not None:
            vx = (drag_start_world[0] - drag_cursor_world[0]) * DRAG_VELOCITY_SCALE
            vz = (drag_start_world[1] - drag_cursor_world[1]) * DRAG_VELOCITY_SCALE
            scene.draw_launch_preview(surface, drag_start_world, (vx, vz))
        # Determine gripper state: holding a block OR (in catcher mode)
        # holding a caught ball that's still sitting on the EE.
        holding = executor.held is not None
        if catcher.state == BallCatcher.STATE_COOLDOWN:
            # After a catch, the ball is parked on the EE for the cooldown.
            holding = True
        if args.industrial:
            scene.draw_arm(surface, world, holding=holding, frame_dt=frame_dt)
        else:
            scene_legacy.draw_arm(
                surface, world, holding=holding, frame_dt=frame_dt)
        # Render Arm B (FK-only secondary arm) — fixed pillar on the right.
        if (
            args.industrial
            and executor_b is not None
            and arm_b_rig is not None
            and arm_b_gripper_state is not None
        ):
            scene.draw_arm(
                surface, world,
                holding=executor_b.held is not None,
                frame_dt=frame_dt,
                arm_state=arm_b_rig.arm_state_from_target(),
                anchor_world_x=arm_b_rig.anchor_world_x,
                link_lengths=arm_b_rig.link_lengths,
                gripper_state=arm_b_gripper_state,
            )

        if args.industrial:
            scene.draw_header(surface, mode_label=mode_label, fps=fps)
            scene.draw_side_panel(
                surface, status,
                recent_commands=command_history,
                parsed_json=last_parsed_json,
            )
        else:
            scene_legacy.draw_header(surface, mode_label=mode_label, fps=fps)
            scene_legacy.draw_side_panel(
                surface, status,
                recent_commands=command_history,
                parsed_json=last_parsed_json,
            )
        # Effects overlay (particles, rings, banners) on top of everything.
        effects.update(frame_dt)
        effects.draw(surface, C.FONT_HEADING)
        is_listening = bool(voice_recorder and voice_recorder.recording)
        is_transcribing = bool(voice_recorder and voice_recorder.is_transcribing)
        is_thinking = (parse_thread is not None and parse_thread.is_alive()) or is_transcribing
        footer = scene.draw_footer if args.industrial else scene_legacy.draw_footer
        # While typing, surface command examples so the audience can see the
        # boundary of what's parseable. Idle prompt stays terse.
        if input_active:
            footer_prompt = (
                'Try:  pick red  ·  stack red green blue  ·  put it on the left  ·  '
                'drive right  ·  build a tower  ·  go home'
            )
        else:
            footer_prompt = (
                'Press 2 to type  ·  Press 3 to toggle mic (again to stop)  ·  '
                '"build a tower"'
            )
        footer(
            surface,
            prompt=footer_prompt,
            input_text=input_text,
            input_active=input_active,
            thinking=is_thinking,
            listening=is_listening,
        )

        _present(surface, window)

        # --- fps / headless exit ------------------------------------
        now = time.perf_counter()
        dt = now - last_t
        last_t = now
        if dt > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / dt)

        if args.headless_probe:
            pygame.image.save(surface, args.probe_output)
            print(f"probe written to {args.probe_output}")
            running = False
            break

        if args.bench > 0:
            if dt > 0:
                bench_samples.append(1.0 / dt)
            if now - bench_start >= args.bench:
                running = False

        if args.screenshot_every > 0 and now >= next_screenshot:
            shot_path = f"/tmp/demo_live_{int((now - bench_start) * 1000):06d}ms.png"
            pygame.image.save(surface, shot_path)
            print(f"shot: {shot_path}")
            next_screenshot = now + args.screenshot_every

        frame_errors = 0
        clock.tick(C.FPS)
      except Exception as exc:
        # Self-heal: one bad frame shouldn't drop the whole demo.
        import traceback
        frame_errors += 1
        print(f"[self-heal] frame error #{frame_errors}: {exc}", file=sys.stderr)
        traceback.print_exc()
        if frame_errors > 20:
            print("[self-heal] giving up after 20 consecutive errors", file=sys.stderr)
            running = False
            break
        # Try to recover scene state.
        try:
            world = make_world()
            controller = JointController(world)
            catcher = BallCatcher(world, controller)
            executor = TaskExecutor(world, controller)
            arm_b_rig, controller_b, executor_b, arm_b_gripper_state = _build_arm_b()
            collab = None  # stale executors after reset — restart collab fresh next idle
            for _ in range(5):
                world.step()
            mode_label = "IDLE"
            status.append(f"[auto-recover #{frame_errors}]")
        except Exception:
            pass

    if bench_samples:
        import statistics
        lo, avg, hi = min(bench_samples), statistics.mean(bench_samples), max(bench_samples)
        print(f"fps: min={lo:.1f}  avg={avg:.1f}  max={hi:.1f}  samples={len(bench_samples)}")

    if tele is not None:
        result = tele.close()
        if result is not None:
            tele_path, tele_summary = result
            print(f"telemetry: {tele_path}\n  {tele_summary}")

    if args.state_dump:
        import json
        ball_pos, ball_vel = world.ball_state()
        held = getattr(executor, "held", None)
        terminal_state = {
            "blocks": [
                {
                    "color": b.color,
                    "x": float(b.xz[0]),
                    "z": float(b.xz[1]),
                    "angle": float(b.angle),
                }
                for b in world.blocks
            ],
            "held_color": getattr(held, "color", None) if held is not None else None,
            "base_x": float(world.base_x),
            "ball": {
                "x": float(ball_pos[0]),
                "z": float(ball_pos[1]),
                "vx": float(ball_vel[0]),
                "vz": float(ball_vel[1]),
            },
            "catcher": {
                "catch_count": int(catcher.catch_count),
                "attempt_count": int(catcher.attempt_count),
                "state": str(catcher.state),
            },
            "executor": {
                "busy": bool(executor.busy),
            },
        }
        Path(args.state_dump).write_text(json.dumps(terminal_state, indent=2))
        print(f"state dump: {args.state_dump}")

    pygame.quit()


if __name__ == "__main__":
    main()
