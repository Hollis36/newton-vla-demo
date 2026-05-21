# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_Nothing yet._

## [0.1.0] — 2026-05-21

Initial public release. A 3-minute classroom demo of embodied AI on a
MacBook — no GPU, no cloud.

### Added

#### Phase A — Test safety net

- `tests/test_scripted_flows.py` — 5 end-to-end regression tests for the
  `--scripted catch/pick/stack/vla` flows that assert on the world
  terminal state (not just FPS) via a new `--state-dump` JSON option.
- `tests/test_tasks.py` — 16 unit tests for `TaskExecutor` program
  builders + the `_ease_min_jerk` curve.
- `tests/test_render_smoke.py` — 20 tests that smoke every public
  `draw_*` surface on both the industrial `scene/` package and the
  legacy classroom renderer.

#### Phase B — Refactor

- New `scene/` package (`arm.py`, `world.py`, `chrome.py`) replaces the
  single 1387-line `scene.py`. All three split modules stay under the
  800-line project-rule ceiling.
- New helper modules in `demo_live/`:
  - `bootstrap.py` — Warp kernel prewarm + Arm B construction.
  - `pipeline.py` — single source of truth for the VLA action → arm
    program mapping (`world_snapshot`, `build_plan_from`).
  - `scripted.py` — rehearsal script constants + Arm B idle cycle data.

#### Phase C — Robustness and expressiveness

- Amber banner + footer cheatsheet when a command returns
  `action="unknown"` (R.1, R.2 later make this fast-path responsive).
- Catcher commit-moment ring rendered the frame `committed_target`
  becomes non-None — audience can see the arm's decision instant.
- Voice transcription gets a per-recognizer `operation_timeout`
  (replacing the previous process-wide `socket.setdefaulttimeout` that
  could leak into other in-process socket users).
- Voice failure surfaces an amber banner explaining the timeout instead
  of silently leaving the input box empty.
- `BallCatcher._predict` warns once per pitch (not per frame) when the
  ballistic discriminant goes negative; `World.launch_ball` clamps
  z to `[0, 2]` and velocity magnitude to `MAX_BALL_SPEED = 20 m/s`.

#### Phase D — New features

- **VLA · PARSED side panel** showing `user`, `via`, `latency_ms`,
  `action`, `color`, `colors`, `target`, `reason` for the last command.
  Up to 7 fields visible on both render paths.
- **Four decorative gestures** wired through `pipeline.build_plan_from`:
  `wave`, `point` (left / right / audience), `bow`, `dance`. Available
  via typed text, voice, and the keyword fallback parser.
- **Slow-motion celebration** (1.5 s @ 0.33× dt) after a successful
  catch or after a multi-step program completes. Gated on
  `executor.busy == False` so in-flight waypoints stay visually
  coherent (see R.3 below).
- **`telemetry.py`** — per-event CSV logger writing `logs/demo-<ts>.csv`
  with mode switches, preflight dispatches, VLA calls (with latency +
  backend), voice transcripts, and catch attempts. Exit summary
  prints to stdout. Opt out with `--telemetry-off`.

#### Phase W — Construction refactor

- `bootstrap.make_arm_b(world, *, industrial, anchor_world_x)` — the
  four reset paths (init, R-key, rehearsal `reset:`, self-heal) now
  share one construction site for the secondary FK-only arm.

#### Phase X — Arm B idle loop

- Arm B perpetually cycles gestures whenever its executor is idle and
  no rehearsal is running. Configured via
  `scripted.ARM_B_IDLE_CYCLE` + `scripted.ARM_B_IDLE_PAUSE_S`. Disable
  with `--no-arm-b-idle`. Automatic in scripted / bench modes.

#### Phase Y — Workpiece shuttle

- New "workpiece" 5th block placed at `x=2.0` (inside Arm B's reachable
  zone). Arm B's idle cycle was upgraded from decorative gestures to
  ping-pong shuttling the workpiece between `x=1.5` and `x=2.5` — looks
  like real industrial pick-and-place.

#### Test growth

- Round T added `test_effects.py` (19) and `test_control.py` (13).
- Round U added `test_catcher.py` (18).
- Round V added `test_vla_subprocess.py` (17).
- Round X added `test_scripted_constants.py` (7).
- Final suite: **214 tests / 102 s wall clock / 100 % passing**.

### Changed

- **`scene.py` 1387 → 0 lines** by splitting into `scene/arm.py` (660),
  `scene/world.py` (228), `scene/chrome.py` (238) + the re-export
  `scene/__init__.py`.
- **`__main__.py` 1066 → 1139 lines** after consolidating helper
  extractions (the bootstrap / pipeline / scripted extractions removed
  ~95 lines but the C, D, R, S, T, X, Y features added new code; net
  cost roughly +75 lines for substantially more functionality).
- Industrial side-panel `AI · PARSED` block expanded from 5 rows × 24
  chars to 7 rows × 36 chars so the new `user` / `via` / `latency`
  fields fit alongside the existing parse output.
- Block out-of-bounds recovery threshold lifted from `|x| > 2.2` to
  `|x| > 3.0` to make room for Arm B's `x=2.5` shuttle endpoint.

### Fixed

#### CRITICAL

- **R.1** — `_fire_parse` preflight action whitelist had
  `{pick, place, stack, drive, home}` but the new gestures were never
  added. As a result `_keyword_fallback` would return `action="wave"`
  but preflight would coerce it back to `"unknown"`, so all four
  gestures had to wait 7–15 s for Claude before the arm moved.
- **R.2** — `_fire_parse` filtered `pre_colors` through `KNOWN_COLORS`
  unconditionally. For the `point` gesture, `colors` carries the
  direction (`left` / `right` / `audience`), not a colour — so every
  `point` command silently fell back to the `left` default.

#### HIGH

- **R.3** — Slow-motion was triggered unconditionally on the catch /
  done falling edge, but `TaskExecutor.update` time-tracks via
  `time.perf_counter()` (not `dt`), so in-flight pick / stack segments
  would visually desynchronize when the catch slow-mo halved `dt`.
  Gated slow-mo on `executor.busy == False`.
- **R.4** — Pressing `2 Enter` twice quickly created two `parse_thread`
  daemon threads writing to the same `parse_result` dict. The older
  worker could clobber the newer one's result. Added a generation
  counter so stale workers drop their results on completion.
- **R.5** — `test_scripted_catch` asserted `catch_count >= 1` over an
  8 s window — flaky if XPBD jitter tightened catch tolerance.
  Split into two tests (auto-launcher fired, ≥ 50 % caught) over
  12 s.

#### MEDIUM / LOW

- **R.6** — `voice.transcribe` replaced `socket.setdefaulttimeout` with
  `recognizer.operation_timeout` so the timeout no longer leaks into
  other in-process socket users.
- **R.7** — Rehearsal `arm_b:` branch now calls
  `pipeline.build_plan_from` instead of duplicating dispatch logic.
  Arm B automatically picks up new actions (gestures + drive).
- **R.8** — `telemetry._sanitize` prefixes cells starting with
  `= + - @ \t` with a single quote so Excel does not evaluate them
  as formulas when opening the debrief CSV.
- **R.9** — Added `tests/test_pipeline.py` with 20 tests covering every
  action branch — would have caught R.1 immediately.
- **R.10** — `telemetry.TelemetryLogger` type annotations changed from
  `TextIOBase | None` / `csv.writer | None` to `IO[str] | None` /
  `Any` (the originals lied about the runtime types).
- **Y.1** — `TaskExecutor._ensure_reachable` early-exits for
  fixed-base arms (Arm B). The previous unconditional `make_drive`
  call would mutate `world.drive_to` and yank Arm A's mobile base
  whenever Arm B picked a block.

#### Polish

- **S.1** — Removed dead `_request_exit` / `_finish` stubs.
- **S.2** — Replaced `O(n²)` `world.blocks.index(block)` with
  `enumerate` in the out-of-bounds recovery loop.
- **S.3** — `launch_ball` clamps velocity magnitude to 20 m/s.
- **S.4** — Telemetry now logs the preflight dispatch, not just
  Claude's eventual response. The CSV now explains "arm moved at
  T+1 ms while Claude returned at T+9.4 s".

### Documentation

- `README.md` — full landing-page redesign with hero GIF, badges,
  three-mode gallery, ASCII hybrid-pipeline diagram, architecture +
  module table, test matrix, performance table, design notes.
- `docs/report.tex` / `report.pdf` — 18-page LaTeX design report with
  redrawn TikZ layered architecture diagram and 4-lane VLA timing
  swimlane diagram.
- `docs/slides.tex` / `slides.pdf` — 24-page beamer defense deck
  mirroring the report structure.
- `docs/figures/` — 7 curated screenshots plus the animated
  `showcase.gif` used as the README hero.
- `demo_live/REHEARSAL.md` — 3-minute on-stage script with optional
  Beat 5 gesture flourish and troubleshooting table.

[Unreleased]: https://github.com/Hollis36/newton-vla-demo/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Hollis36/newton-vla-demo/releases/tag/v0.1.0
