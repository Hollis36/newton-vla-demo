# Newton VLA Live Demo

A 3-minute classroom demo of embodied AI on a MacBook:
NVIDIA Newton physics engine + 2D pygame UI + Claude CLI as the VLA brain.

See [REHEARSAL.md](REHEARSAL.md) for the stage script.

## Quick start

```bash
cd /Users/kingcode/Documents/Newton/newton
uv run --extra demo python -m demo_live --fullscreen
```

The default launch uses the legacy single-arm classroom whiteboard view.
For the newer dual-arm workstation view:

```bash
uv run --extra demo python -m demo_live --fullscreen --industrial
```

Controls during the demo:

- `1` — Ball-catch mode (MPC, no AI). Click-and-drag to throw.
- `2` — Talk-to-arm mode (VLA via Claude CLI, fallback keyword parser)
- `3` — Toggle microphone input
- `F5` — One-key auto-rehearsal (warm-up before going on stage)
- `R` — Reset scene
- `Q` / `Esc` — Quit

### Commands that work in mode `2`

| Phrase | Action |
|--------|--------|
| `pick up the red block`, `grab green` | Pick up a colored block |
| `put it on the left`, `place at x=0.5` | Place the held block |
| `stack red green and blue`, `build a tower` | Pick + stack 2-4 blocks |
| `drive right`, `drive to red` | Move the mobile base |
| `wave`, `say hi`, `挥手` | Decorative gesture — arm waves |
| `point at the audience`, `point right`, `指向左` | Arm extends and holds |
| `bow`, `鞠躬` | Arm bows |
| `dance`, `跳舞` | Short rhythmic sequence |
| `go home`, `回位`, `reset` | Return to rest pose |

When a command isn't recognized the demo flashes an amber banner with
quick examples; the input box footer also surfaces a cheatsheet while
you're typing.

### Visual feedback for the audience

- **Amber ring** on the end-effector the moment the catcher locks an
  intercept point. Lets the audience see the "decision".
- **Slow-motion (0.33×) for 1.5 s** after a successful catch or after a
  multi-step program (e.g. building a tower) finishes — long enough to
  appreciate the moment without dragging the pacing.
- **Side panel** continuously shows the last parsed command with backend
  (Claude / preflight keyword / fallback), latency, and the reasoning.

## Architecture

```
demo_live/
├── __main__.py        Entry point — pygame loop, events, mode dispatch
├── bootstrap.py       Warp kernel + Python fast-path prewarming
├── pipeline.py        world_snapshot, build_plan_from (VLA → arm program)
├── scripted.py        Static rehearsal scripts (default + F5 hotkey)
├── telemetry.py       Per-event CSV logger for post-class debrief
├── config.py          Design tokens (colors, fonts, layout)
├── physics.py         Newton world, 3-link arm, blocks, ball kinematics
├── control.py         Slew-rate-limited PD target tracker
├── ik.py              Closed-form 3-link planar IK
├── catcher.py         MPC-style ball-intercept state machine
├── tasks.py           Pick / Place / Stack + gestures (wave/point/bow/dance)
├── vla.py             Claude CLI subprocess + keyword fallback parser
├── voice.py           Mic capture + Google Web Speech + fuzzy snap
├── effects.py         Particle bursts / rings / banners
├── sfx.py             Sound effects
├── scene/             Industrial dual-arm renderer (split into 3 modules)
│   ├── arm.py         Arm pedestal + base + links + gripper
│   ├── world.py       Ground, ball, trajectory, blocks
│   └── chrome.py      Header, side panel, footer
├── scene_legacy.py    Default classroom whiteboard renderer (single file)
├── render.py          Primitives: sketch line / rect / circle / text
├── fonts/             Kalam + Patrick Hand (Google Fonts, academic whiteboard)
└── REHEARSAL.md       3-minute stage script
```

### Flow

```
user Enter in mode 2
     ↓
parse_command (threaded)
 ├── claude --print → JSON plan   (preferred)
 └── keyword fallback              (reliable)
     ↓
TaskExecutor.queue(make_pick / make_place / make_stack)
     ↓
JointController (PD target tracker)
     ↓
Newton XPBD solver (arm dynamics)
     ↓
pygame renderer @ 60 fps
```

## Headless smoke tests

```bash
# basic boot + render test
uv run --extra demo python -m demo_live --headless-probe

# fps benchmark (5 s)
SDL_VIDEODRIVER=dummy uv run --extra demo python -m demo_live --bench 5

# scripted scenarios (same as the rehearsal beats)
SDL_VIDEODRIVER=dummy uv run --extra demo python -m demo_live --scripted catch --bench 10
SDL_VIDEODRIVER=dummy uv run --extra demo python -m demo_live --scripted pick --bench 5
SDL_VIDEODRIVER=dummy uv run --extra demo python -m demo_live --scripted stack --bench 24
SDL_VIDEODRIVER=dummy uv run --extra demo python -m demo_live --scripted vla \
    --vla-command "stack a tower" --bench 24

# dump terminal world state to JSON (used by tests/test_scripted_flows.py)
SDL_VIDEODRIVER=dummy uv run --extra demo python -m demo_live \
    --scripted pick --bench 6 --state-dump /tmp/world.json
```

## Telemetry

Every live (non-bench, non-headless, non-scripted) session writes a CSV
to `logs/demo-<YYYYmmdd-HHMMSS>.csv` for post-class debrief — one row per
mode switch, preflight dispatch, VLA call, voice transcript, and catch
attempt. The session also prints a summary line on exit:

```
telemetry: logs/demo-20260521-123022.csv
  VLA: 1 calls (avg 9374ms, 0 fallback); catches: 8/8; mode switches: 1
```

Disable with `--telemetry-off` if you don't want the file (e.g. during
last-minute rehearsals on stage).

## Unit tests

```bash
uv run --extra demo python -m unittest discover -s demo_live/tests -v
```

Coverage (138 tests, ~80 s wall clock):

- Closed-form IK round-trip (FK∘IK ≈ id)
- VLA keyword fallback parser (English + Chinese, gestures + functional)
- Voice fuzzy-snap post-processor (78 cases)
- TaskExecutor program builders (pick/place/stack/drive + gestures)
- `pipeline.build_plan_from` — every action enum (regression guard for
  the preflight whitelist + point-direction filter bugs)
- End-to-end `--scripted` flows with `--state-dump` JSON assertion
- Headless render smoke (both scene/ and scene_legacy.py paths)
- Telemetry CSV format + formula-injection neutralization

The tests don't touch the microphone or network.

## Lint

```bash
ruff check demo_live/                # audit
ruff check demo_live/ --fix          # auto-fix
ruff format demo_live/               # style only
```

Config in `demo_live/pyproject.toml` (ruff + pytest). Convenience
shortcuts in `demo_live/Makefile` (`make test`, `make lint`, `make bench`).

## Measured performance

On Apple Silicon (CPU-only, no GPU):

| Scenario | min | avg | max | Samples |
|----------|-----|-----|-----|---------|
| IDLE bench 20 s | 31.5 | 60.7 | 75.9 | 1211 |
| Scripted catch 10 s | 28.2 | 59.6 | 72.8 | 594 |
| Scripted pick 8 s | 41.7 | 60.7 | 70.3 | 485 |
| Scripted stack 25 s | 24.8 | 59.2 | 74.9 | 1476 |
| Scripted VLA 25 s | 24.0 | 59.6 | 75.1 | 1484 |
| Rehearsal 60 s | 2.9 | 58.7 | 76.0 | 3494 |

FPS target = 60 Hz (capped by `clock.tick(60)`). Avg ≥ 58 across all
scripted flows.

## Design notes

- **Ball is Python-integrated** (not XPBD): XPBD ignores `body_qd` as an
  initial velocity, so we drive the ball's pose analytically each frame.
- **Blocks are Python-stored** (not Newton bodies): kinematic teleporting
  with mass>0 destabilizes XPBD and with mass=0/is_kinematic produces NaN
  on large jumps. Python-side storage gives perfect scripted motion.
- **Arm uses Newton body_q for rendering** (not custom FK): the collision
  shapes live in Newton's frame; rendering from it guarantees the sprite
  matches the physics.
- **Joint axis is `(0, -1, 0)`**: Newton's right-hand Y rotation sends +X
  toward -Z, opposite of our sign convention — flip the axis once at the
  joint so positive REST_POSE angles make the arm point up.
- **VLA is timeout-safe**: `claude --print` runs in a daemon thread with
  2.5 s timeout. If it stalls, the keyword parser handles the command
  without blocking the UI — the "Thinking..." dots keep the user informed.
- **Hybrid parse pipeline**: every typed/spoken command runs through the
  keyword preflight first (~1 ms, drives the arm immediately) and then
  Claude as a background refinement (~2-10 s). Claude can only override
  the preflight if it's still in flight by the time it returns; the
  `parse_thread` generation counter ensures a stale slow worker can never
  clobber a fresher command's result.
- **Slow-motion is gated on `executor.busy=False`**: scaling `frame_dt`
  by 0.33 also affects controller PD, ball integration, and base drive.
  But `executor.update` time-tracks via `time.perf_counter()` instead of
  dt, so a slow-mo triggered mid-pick would visibly desynchronize the
  waypoint segments from the arm physics. Gating on idle keeps the
  visual coherent.

See [REHEARSAL.md](REHEARSAL.md) for on-stage troubleshooting.
