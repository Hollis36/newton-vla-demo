<div align="center">

# Newton VLA Live Demo

**A 3-minute classroom demo of embodied AI on a MacBook — no GPU, no cloud.**

NVIDIA Newton physics engine • pygame 2D UI • Claude CLI as the VLA brain.

[![CI](https://github.com/Hollis36/newton-vla-demo/actions/workflows/tests.yml/badge.svg)](https://github.com/Hollis36/newton-vla-demo/actions/workflows/tests.yml)
[![Pages](https://img.shields.io/badge/pages-live-22c55e?logo=github)](https://hollis36.github.io/newton-vla-demo/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-238%20passing-22c55e)](#testing)
[![FPS](https://img.shields.io/badge/fps-60.5%20avg-06b6d4)](#performance)
[![Lines](https://img.shields.io/badge/code-7730%20lines-64748b)](#architecture)
[![Newton](https://img.shields.io/badge/Newton-XPBD-76b900?logo=nvidia&logoColor=white)](https://github.com/newton-physics/newton)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

<img src="docs/figures/showcase.gif" alt="Newton VLA demo cycling through IDLE → CATCH → STACK → VLA → classroom modes" width="92%">

**🌐 Live site:** [hollis36.github.io/newton-vla-demo](https://hollis36.github.io/newton-vla-demo/)
**▶ 52 s auto-recorded rehearsal:** [demo_rehearsal.mp4](docs/figures/demo_rehearsal.mp4) (723 KB, 1280×720)

> *Audience types* `build a tower of red green and blue` *. Claude parses it in 9.4 s. The arm starts moving in 1 ms. Both are visible side by side.*

</div>

---

## TL;DR

- **Three interaction modes** in one demo: classical MPC ball-catch (no AI), natural-language pick & stack (Claude VLA), and decorative gestures (wave / point / bow / dance).
- **Hybrid VLA pipeline** runs a keyword preflight (~1 ms) in parallel with `claude --print` (~9.4 s). The arm acts on the preflight; Claude returns later as an "intelligent reviewer."
- **Dual-arm industrial mode** adds a second fixed-base arm; with `--collab` the two arms run a continuous collaborative tower build (Arm A fetches → handoff → Arm B stacks → roles reverse to tear it down) whenever the stage is idle.
- **`--real-blocks` mode** simulates the colored blocks as genuine Newton rigid bodies — they stack, topple and collide — with a KINEMATIC-toggle grasp (XPBD has no weld constraints).
- **`--experiment` mode** turns Arm B into a physics lecturer: it stacks towers with a growing per-layer offset and real dynamics decides when the center of mass leaves the base — stable at 4 cm/layer, genuine collapse at 9 cm, with a live CoM plumb-line overlay.
- **238 unit + integration tests**, 60.5 fps average on Apple Silicon CPU-only, no GPU required.
- **Single-binary install** via `uv` — boots from cold in ~2 s after Warp kernel cache warms up.

---

## Why this project is interesting

**For instructors and education researchers.** It takes a classroom-level
demonstration of embodied AI — usually the kind of artefact that needs a
dedicated lab, an Ubuntu workstation with a CUDA-capable GPU, and a
hand-picked grad student to babysit — and collapses it into a 3-minute
script that runs on the same MacBook the lecturer used to write the
slides. There is no cloud round-trip, no API key to manage, and the
entire vocabulary (English + 中文, gestures included) is documented and
testable. A volunteer from the front row can drive the arm.

**For systems engineers.** The interesting work is in *latency
decoupling*. A foundation model like Claude takes 2–10 seconds to parse
a sentence — orders of magnitude beyond the 60 fps frame budget. The
naive approach (block the renderer until the LLM returns) is unusable
on stage. This project's hybrid pipeline solves it: a deterministic
1 ms keyword preflight queues the arm immediately, while Claude refines
in a background thread; their results are reconciled when Claude returns,
with a generation counter preventing stale workers from clobbering newer
commands. The audience perceives instant response with intelligent
backfill. This pattern — *cheap-and-deterministic in the foreground,
expensive-and-smart in the background* — generalises far beyond robotics.

**For Python/games engineers.** It's a complete reference for how to
build a 60 fps interactive demo on top of NVIDIA Newton without fighting
the XPBD solver: a worked example of when to use the physics engine
(arm dynamics, contact) vs. when to Python-integrate (the ball, blocks
that need to teleport without contact explosions), how to layer
`min-jerk + back-ease-out` curves for *expressive* motion that doesn't
feel robotic, and how to keep `__main__.py` event handling readable
with a hybrid VLA + voice + telemetry pipeline. 238 tests, including
`test_pipeline.py` that retroactively catches the exact action-enum
mismatch class that produced this project's two CRITICAL bugs.

**For job applicants and grad students.** The 8-round development log
(see [CHANGELOG.md](CHANGELOG.md)) is a candid record of how a
real-world software project actually evolves — the safety net before
the refactor, the bugs surfaced by parallel professional reviewers, the
trade-off between an ambitious architectural rewrite and pragmatic
extraction, the iterative polishing of TikZ diagrams that didn't quite
look right the first time. There's nothing aspirational about this
list; everything in it was actually done, committed, and tested.

---

## Quick start

### 1. Clone this repo and the Newton engine side by side

```bash
# Newton isn't on PyPI yet — clone the head from upstream as a sibling.
git clone https://github.com/Hollis36/newton-vla-demo.git
git clone https://github.com/newton-physics/newton.git
cd newton-vla-demo
uv sync --extra demo                          # pygame-ce + voice deps
```

### 2. Run it

The Makefile injects the sibling Newton clone on the fly via
`uv run --with "newton[sim] @ ../newton"` (override the location with
`make NEWTON=/path/to/newton <target>`):

```bash
make collab         # dual-arm + collaborative tower build (best first impression)
make industrial     # fullscreen dual-arm view (recommended for projection)
make demo           # default classroom whiteboard view
make real-blocks    # dual-arm with real rigid-body blocks
make collab-real    # collab on real blocks (experimental — they topple!)
make experiment     # Arm B's offset-tower stability lecture (real physics)
```

Or equivalently, by hand:

```bash
uv run --extra demo --with "newton[sim] @ ../newton" \
  python -m demo_live --fullscreen --industrial
```

### Optional: Claude CLI for open-vocabulary VLA

Install [`claude --print`](https://claude.com/claude-code) and the demo will
route every typed command through it for richer parsing. **The keyword
fallback handles every rehearsed command on its own**, so without Claude the
demo runs in `fallback` backend mode with no loss of functionality — just
a "via fallback" tag in the AI · PARSED side panel instead of "via claude".

### Live controls

| Key | Action |
|---|---|
| `1` | Ball-catch mode (MPC, no AI). Click-and-drag to throw. |
| `2` | Talk-to-arm mode. Type a command, press Enter. |
| `3` | Toggle microphone (voice input via Google Web Speech). |
| `R` | Reset scene + arm. |
| `F5` | One-key auto-rehearsal (warm-up before going on stage). |
| `Q` / `Esc` | Quit. |

---

## What you can say to the arm

```
pick up the red block          →  arm picks red
put it on the left              →  arm places held block at x=-0.6
stack red green and blue        →  arm builds a 3-block tower
build a tower                   →  default RGB tower
drive to the blue block         →  base moves under blue
wave / say hi / 挥手             →  decorative wave gesture
point at the audience           →  arm extends and holds
take a bow / 鞠躬                →  arm bows
dance for us / 跳舞              →  4-beat rhythmic sequence
go home / 回位 / reset           →  back to rest pose
```

English and 中文 are both supported via the keyword fallback parser; Claude handles the full open vocabulary on top.

---

## The three demo modes

<table>
<tr>
<td width="33%" align="center">

### BALL CATCH<br><sub>MPC, no AI</sub>

<img src="docs/figures/catch_industrial.png" width="100%"><br>

Closed-form ballistic intercept. Trajectory sampling (blue) + intercept-point ring (orange).<br>
**62–82 %** measured catch rate.

</td>
<td width="33%" align="center">

### TALK TO ARM<br><sub>VLA</sub>

<img src="docs/figures/stack_industrial.png" width="100%"><br>

Natural language → JSON action → arm program. Hybrid pipeline runs preflight + Claude in parallel.<br>
**1 ms** to first motion.

</td>
<td width="33%" align="center">

### GESTURES<br><sub>Decorative</sub>

<img src="docs/figures/classroom_view.png" width="100%"><br>

Wave, point, bow, dance — for ending the show or filling time between volunteer prompts.<br>
**4** gesture vocabulary.

</td>
</tr>
</table>

---

## How the hybrid VLA pipeline works

Claude latency (2–10 s) is way over the 60 fps frame budget. We decouple acting from reasoning:

```
 input ────●─────────────────────────────────────────────────────────
           │
           │  preflight ──[▮]→ 1 ms → arm starts moving             ◀── lane 2
           │
           │  Claude    ──[████████████████████████]──◉ 9.4 s       ◀── lane 3
           │            (refining…)                  (returns)
           │
           │  arm       ──[██████████████████████████████████████ ─→  ◀── lane 4
           │            pick red → stack → … (12 s+ of motion)
           │
           └───────────────────────────────────────────────────────►  t (s)
              0      2      4      6      8     10     12
```

1. **Synchronous keyword preflight** in `_keyword_fallback` queues an arm plan in ~1 ms. The arm is already moving.
2. **`claude --print --model sonnet`** runs in a daemon thread for ~9 s. When it returns, the result is compared with the preflight — same action → silent confirm; different → log only (the preflight already executed).
3. **Generation counter** on `parse_result["gen"]` prevents a stale slow worker from clobbering a fresher command.

To the audience this looks like **instant response with intelligent refinement**, even though Claude is genuinely slow.

---

## Industrial dual-arm mode (`--industrial`)

<img src="docs/figures/industrial_view.png" width="100%">

* **Arm A** (left, on tracked mobile base) — Newton XPBD physics, drives the audience commands.
* **Arm B** (right, fixed pedestal) — FK-only, perpetually shuttles a dedicated *workpiece* block between x = 1.5 ↔ 2.5 in its reachable zone.
* Both arms **share `world.blocks`** but never compete: Arm B's workpiece lives outside Arm A's typical workspace, and Arm B's `TaskExecutor` short-circuits the base-drive step that would otherwise yank Arm A around.

The two arms move **completely in parallel**: when you throw a ball at Arm A, Arm B keeps shuttling. When you tell Arm A to build a tower, Arm B keeps shuttling.

### Two-arm collaborative build (`--collab`)

Add `--collab` and Arm B's mindless shuttle is replaced by a **purposeful
relay** whenever the stage goes idle: Arm A fetches teaching blocks from the
field and sets them on a handoff slot; Arm B picks from the slot and stacks a
tower in its own reach zone; after a short admire beat the roles reverse to
tear it down, then it loops. The coordinator (`collab.py`) only sequences
high-level pick/place programs onto the two executors, gated on a single-slot
handoff — and it **yields the instant you do anything** (key press, voice,
in-flight parse), releasing any held block and handing both arms back.

Run it on the default teleport blocks for the show loop: placements are
exact, cycle after cycle. Combining `--collab --real-blocks` is physically
honest but **experimental** — across build/teardown cycles the genuinely
rigid blocks bounce on release, slide into the parked workpiece and topple
(real dynamics, scrappy stagecraft). Benchmarks below cover both.

### Real rigid-body blocks (`--real-blocks`)

By default the blocks are Python-stored and teleported (rehearsal-safe).
With `--real-blocks` every block becomes a genuine Newton rigid body: towers
genuinely **stack, topple and collide**. Grasping uses a KINEMATIC toggle —
XPBD has no weld/equality constraints, so a held block is flipped to
`BodyFlags.KINEMATIC` and its pose prescribed from the gripper each frame,
then flipped back to `DYNAMIC` on release so it settles onto whatever is
below. Double-grab, release-without-grab and out-of-bounds-while-held are
all guarded and tested.

### The stability experiment (`--experiment`)

Arm B becomes a physics lecturer. Each round it stacks its three grey
workpieces into a tower whose layers step sideways — 0 cm, then 4 cm, then
9 cm per layer — and **real rigid-body dynamics delivers the verdict**: with
cubes of half-width 10 cm, the top two layers' combined center of mass sits
`1.5 d` from the bottom block, so the tower must topple once the per-layer
offset `d` exceeds ~6.7 cm. The 4 cm round survives, the 9 cm round
collapses on stage, and a live overlay draws the CoM plumb line against the
support-base bracket so the audience can see the criterion flip (the line
turns amber the moment the projection leaves the base). After each verdict
Arm B tidies the parts back to their slots and runs the next round; a
collapse restarts the lecture from the aligned tower. The bracketing claim
itself is pinned by a real-XPBD regression test, and Arm A stays free for
audience commands throughout — `--experiment` implies `--industrial
--real-blocks` and never borrows the left arm.

---

## Architecture

```
 ┌─────────────────────────────────────────────────────────────────┐
 │  Input    keyboard · mouse · microphone                          │
 └────────────────────────────┬────────────────────────────────────┘
                              │
 ┌────────────────────────────▼────────────────────────────────────┐
 │  Parser   vla.py · voice.py · pipeline.py                        │── tel ─┐
 └────────────────────────────┬────────────────────────────────────┘        │
                              │                                              │
 ┌────────────────────────────▼────────────────────────────────────┐        │
 │  Control  tasks.py · control.py · catcher.py                     │── tel ─┤
 └────────────────────────────┬────────────────────────────────────┘        │
                              │                                              │
 ┌────────────────────────────▼────────────────────────────────────┐        │
 │  Physics  physics.py · Newton XPBD                               │── tel ─┤
 └────────────────────────────┬────────────────────────────────────┘        │
                              │                                              │
 ┌────────────────────────────▼────────────────────────────────────┐        │
 │  Render   scene/ · scene_legacy · effects · sfx                  │── tel ─┘
 └─────────────────────────────────────────────────────────────────┘   telemetry.py
```

**4 helper modules** (`bootstrap`, `pipeline`, `scripted`, `telemetry`) + **1 new package** (`scene/{arm,world,chrome}`) keep the main pygame loop focused on event dispatch.

| Module | Lines | Role |
|---|---:|---|
| `__main__.py`     | 1358 | pygame loop, events, mode dispatch |
| `scene/arm.py`    |  675 | industrial robot arm render |
| `scene_legacy.py` |  671 | default classroom whiteboard renderer |
| `physics.py`      |  660 | Newton world + 3-DOF arm + real-blocks grasp |
| `voice.py`        |  512 | mic + Google Web Speech + fuzzy snap |
| `vla.py`          |  467 | Claude CLI subprocess + keyword fallback |
| `tasks.py`        |  432 | pick / place / stack / gesture builders |
| `render.py`       |  373 | sketch-style primitives (precomputed jitter) |
| `scene/world.py`  |  335 | ground / ball / trajectory / blocks / CoM overlay |
| `catcher.py`      |  271 | MPC + closed-form ballistic intercept |
| `effects.py`      |  247 | particles / rings / banners / trail |
| `scene/chrome.py` |  237 | header / side panel / footer |
| `control.py`      |  215 | PD slew + idle wobble + NaN rejection |
| `experiment.py`   |  194 | offset-tower stability lecture coordinator |
| `config.py`       |  171 | palette, layout + canonical block spawn slots |
| `collab.py`       |  167 | two-arm collaborative build coordinator |
| `telemetry.py`    |  163 | CSV logger + exit summary |
| `sfx.py`          |  132 | procedural sound effects |
| `scripted.py`     |  110 | rehearsal scripts + Arm B idle cycle data |
| `bootstrap.py`    |   93 | Warp prewarm + Arm B construction |
| `ik.py`           |   91 | closed-form 3-link planar IK |
| `pipeline.py`     |   84 | action → arm program (single source of truth) |
| **Total (excl. tests)** | **7730** | |

---

## Testing

238 unit + integration tests, **~105 s** wall clock, **100 % passing** on every commit.

```bash
make test    # uv run --extra demo --with "newton[sim] @ ../newton" \
             #   python -m unittest discover -s demo_live/tests -v
```

| Test file | Tests | Focus |
|---|---:|---|
| `test_tasks.py`              | 27 | program builders + 4 gestures + grasp callbacks |
| `test_vla_parser.py`         | 24 | keyword parser (English + Chinese) |
| `test_voice_fuzzy.py`        | 21 | 78 noisy transcripts via subTests (peter→pick, …) |
| `test_pipeline.py`           | 20 | every action enum branch |
| `test_render_smoke.py`       | 21 | both render paths, all public `draw_*` |
| `test_effects.py`            | 19 | particle/ring/banner/trail lifecycle |
| `test_catcher.py`            | 18 | ballistic math + state machine |
| `test_vla_subprocess.py`     | 17 | Claude CLI mock (timeout, malformed JSON, fences) |
| `test_control.py`            | 13 | PD slew + rate clamp + NaN rejection |
| `test_ik.py`                 | 10 | FK ∘ IK ≈ id |
| `test_telemetry.py`          | 10 | CSV format + formula-injection neutralisation |
| `test_experiment.py`         |  9 | stability lecture: rounds, verdicts, XPBD topple pin |
| `test_real_blocks.py`        |  9 | KINEMATIC grasp, stacking, OOB recovery guards |
| `test_scripted_constants.py` |  7 | Arm B idle cycle + rehearsal data integrity |
| `test_scripted_flows.py`     |  6 | end-to-end `--scripted` flows |
| `test_collab.py`             |  5 | two-arm relay: build, teardown order, loop |
| `test_display_mode.py`       |  2 | CLI argument parsing |
| **Total**                    | **238** | |

### Headless smoke

```bash
SDL_VIDEODRIVER=dummy uv run --extra demo --with "newton[sim] @ ../newton" python -m demo_live \
  --scripted vla --vla-command "stack a tower" --bench 25
# fps: min=24.0  avg=59.6  max=75.1  samples=1484
```

---

## Performance

Apple Silicon, **CPU-only** (no GPU):

| Scenario          | min  | **avg** | max  | samples |
|-------------------|-----:|--------:|-----:|--------:|
| IDLE 20 s         | 31.5 | **60.7** | 75.9 | 1211 |
| Scripted catch    | 28.2 | **59.6** | 72.8 |  594 |
| Scripted pick     | 41.7 | **60.7** | 70.3 |  485 |
| Scripted stack    | 24.8 | **59.2** | 74.9 | 1476 |
| Scripted VLA      | 24.0 | **59.6** | 75.1 | 1484 |
| Scripted VLA + real-blocks | 33.3 | **56.9** | 123.0 | 1132 |
| Idle collab relay, 90 s | 29.5 | **55.0** | 94.7 | 4918 |
| Idle collab relay + real-blocks, 90 s | 30.0 | **56.8** | 116.7 | 5090 |
| 60 s rehearsal    |  2.9 | **58.7** | 76.0 | 3494 |

After the v0.2 solver tuning (fewer iterations/substeps, a teleport-mode
`collide()` skip, and precomputed jitter tables in `render.py`), Newton
XPBD costs **~0.3 ms/frame** in the default teleport mode — down from
11.9 ms — and **~5 ms** with `--real-blocks` (the cost is per-substep
kernel-launch overhead, not body count). Uncapped headless throughput
is ~279 fps; the 60 fps cap is the binding constraint in practice.

---

## Documentation

* [**Design report**](docs/report.pdf) (18 pages, LaTeX) — full architectural breakdown, algorithm derivations, design decisions, evaluation, and limitations.
* [**Defense slides**](docs/slides.pdf) (24 pages, beamer 16:9) — walkthrough deck.
* [**REHEARSAL.md**](REHEARSAL.md) — 3-minute on-stage script with pre-flight checklist and troubleshooting.
* [**Makefile**](Makefile) — `make demo`, `make industrial`, `make collab`, `make rehearsal`, `make test`, `make bench`.

---

## Design notes

* **Ball is Python-integrated** (not XPBD): XPBD silently zeros `body_qd` on first step in some Newton versions, so the ball is driven analytically each frame: `z(t) = z₀ + v_z·t − ½ g·t²`.
* **Blocks are Python-stored by default**: kinematic teleporting with `mass > 0` destabilises XPBD, and `mass = 0 / is_kinematic` produces NaN on large jumps. Python-side storage gives perfect scripted motion. `--real-blocks` opts into genuine rigid bodies when you want towers that topple.
* **Grasping is a KINEMATIC toggle, not a weld**: XPBD doesn't support weld/equality constraints, so in `--real-blocks` mode a held block is flipped to `BodyFlags.KINEMATIC` (pose prescribed from the gripper each frame, still collidable) and back to `DYNAMIC` on release — clean pick → carry → place → settle with no constraint spray.
* **Teleport mode skips `collide()`**: with no real contacts to find (arm is a world-anchored PD chain in free space, ball is analytic, blocks are Python), the per-substep broad/narrow-phase kernel launches were pure overhead — a prebuilt empty contacts object is reused instead, cutting `step()` from 4.7 ms to ~0.3 ms.
* **Arm renders from `body_q` not custom FK**: the collision shapes live in Newton's frame; rendering from it guarantees the sprite always matches the physics.
* **Joint axis is `(0, -1, 0)`**: Newton's right-hand Y rotation sends +X toward −Z, opposite of our sign convention — flipped once at the joint so positive `REST_POSE` angles make the arm point up.
* **Slow-mo gated on `executor.busy = False`**: scaling `frame_dt` by 0.33 also affects controller PD and ball integration, but `executor.update` time-tracks via `time.perf_counter()` (not `dt`). Triggering slow-mo mid-pick would desynchronize the waypoint clock from the arm — the gate keeps the visual coherent.

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Built on a MacBook. No cloud. No GPU.<br>
Powered by [Newton](https://github.com/newton-physics/newton), [Claude](https://claude.com/claude-code), and a lot of `min-jerk` curves.

</div>
