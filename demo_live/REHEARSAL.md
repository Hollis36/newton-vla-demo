# Newton VLA Live Demo · 3-Minute Rehearsal Script

**Audience**: classroom (students + instructors)
**Duration**: 3:00
**Screen**: Mac mirrored, full-screen `demo_live` in academic whiteboard style
**Goal**: "From classical control to embodied AI, on one laptop."

---

## Pre-Flight (before class)

1. Open terminal, `cd /Users/kingcode/Documents/Newton/newton`
2. Run `uv run python -m demo_live --fullscreen` once to pre-warm Warp kernels
   (first boot compiles JIT; takes ~10 s, later boots < 2 s).
3. Quit with `Q`. The kernel cache under `~/Library/Caches/warp/` is now hot.
4. Verify `claude --print --model sonnet` is on your `$PATH` (required for the
   LLM path). If not, the keyword fallback still handles all rehearsed
   commands.
5. Connect to the projector. Set Mac display to **mirror** at 1920 × 1080.

## Launch command (on stage)

```bash
cd /Users/kingcode/Documents/Newton/newton
uv run python -m demo_live --fullscreen
```

The demo starts in IDLE mode. You see the 3-DOF arm in rest pose and four
colored blocks on the ground. Status panel says **"Prewarmed."**

---

## Beat 1 · 0:00 – 0:30 · Hook (Ball Catch)

**Say**: "Classical control has been solving this for decades. Watch."

1. Press **`1`**. Mode flips to **BALL CATCH**.
2. Arm assumes the ready stance and first ball is lobbed from the right.
3. Arm catches the ball. Status says `Caught! (1/1)`.
4. Two more throws follow automatically at ~1.3 s cadence. Each caught.
5. After the third catch, press **`R`** to reset the scene.

**Say**: "This is MPC — model, predict, intercept. Now let's put a brain on
top."

## Beat 2 · 0:30 – 2:10 · Audience asks the arm to work (VLA)

**Say**: "Who wants to give the arm an instruction? Come up."

First volunteer at the keyboard.

1. Press **`2`**. Mode flips to **TALK TO ARM**. Input box lights up.
2. Volunteer types: **`pick up the red block`** → `Enter`.
3. Footer shows **Thinking...** while `claude --print` parses the command.
   (Takes ~1–2 s; the pause reads as "AI thinking".)
4. Status log shows `← claude XXXms · user asked to pick red`.
5. Arm executes: Approach → Descend → Grip → Lift → hold.

**Say**: "Notice: the student said plain English. No code. The model translated
it to `{action: pick, color: red}`. Now put it down somewhere."

6. Second volunteer. Press **`2`** again.
7. Types: **`put it on the left`** or **`place at -0.6`** → `Enter`.
8. Arm carries the red block and places it at the left side.

## Beat 3 · 2:10 – 2:50 · Crescendo (Stack tower)

**Say**: "One more. Tell it to build something."

Third volunteer.

1. Press **`2`**, type **`build a tower from red, green, and blue`**.
2. Claude parses to `{action: stack, colors: [red, green, blue]}`.
3. Arm picks each block and stacks them. ~14 seconds of continuous motion.

Watch the tower grow. Status log reads the sequence aloud: Approach red →
Descend → Grip + lift → Move above target → Release → Return → Approach green…

## Beat 4 · 2:50 – 3:00 · Close

**Say**: "Physics in [Newton](https://github.com/newton-physics/newton).
Parsing by Claude. Interpolation and IK written by hand. Running entirely on
this Mac, no GPU, no cloud. That's embodied AI on a laptop."

*(applause)*

## Optional Beat 5 · gesture flourish (~10 s, if running long)

If the audience is engaged and you have time, end on a gesture instead of
fading out. Press `2`, then type one of:

| Phrase | Effect |
|--------|--------|
| `wave at the audience` | Arm raises, sweeps left-right twice |
| `take a bow` | Arm folds forward, holds, rises |
| `dance` | 4-beat rhythmic pose sequence |
| `point at the audience` | Arm extends up-and-out, holds 1.5 s |

These hit the keyword preflight (no Claude latency) so the arm starts
moving the instant you press Enter — useful as a "the robot is going off
script" punchline.

---

## Live operator cheatsheet

| Key | Action |
|-----|--------|
| `1` | Ball-catch mode on/off |
| `2` | Enter VLA text mode (type → Enter) |
| `R` | Hard reset scene + arm + blocks |
| `Esc` | Cancel text input |
| `Q` / `Esc` (outside input) | Quit |

| If this happens... | Fix |
|--------------------|-----|
| Arm freezes | Press `R` to reset |
| Claude parse times out (> 2.5 s) | Fallback keyword parser kicks in silently |
| Ball lands on ground | State machine re-arms after 1.3 s; next ball comes |
| Projector mirror is wrong resolution | `System Settings → Displays → Scale to 1920×1080` |
| Arm lunges at audience volunteer | Also press `R`. Then explain the joke. |
| Mic doesn't trigger | Press `3` again to cancel listening; voice times out after 5 s, banner says "VOICE FAILED" — fall back to typing |
| Command not recognized | Amber banner shows "DIDN'T CATCH THAT" + suggestions. Footer also lists examples. |

## Commands the parser handles reliably

Both English and Chinese. Add new colors in `demo_live/physics.py` block_layout
and the parser picks them up automatically.

| Phrase | Parsed as |
|--------|-----------|
| `pick up the red cube` | `pick red` |
| `grab the green one` | `pick green` |
| `put the block on the left` | `place [-1.0, 0]` |
| `place it at x = 0.5` | `place [0.5, 0]` |
| `build a tower` | `stack [red, green, blue]` |
| `stack red then blue` | `stack [red, blue]` |
| `go home` | `home` |
| `拿起红色方块` | `pick red` |
| `搭个塔` | `stack [red, green, blue]` |

## If the network is down

The demo does not need network — `claude --print` uses the user's local Claude
Code subscription, which authenticates offline after first login. The keyword
fallback is always available.

## After the demo

A CSV telemetry file at `logs/demo-<YYYYmmdd-HHMMSS>.csv` captures every
mode switch, preflight dispatch, VLA call (with latency + backend), voice
transcription, and catch attempt — useful for debriefing in the next
class. The exit summary also prints to stdout:

```
telemetry: logs/demo-20260521-123022.csv
  VLA: 1 calls (avg 9374ms, 0 fallback); catches: 8/8; mode switches: 1
```

Pass `--telemetry-off` if you don't want the file (e.g. during a sound-check
walk-through right before going live).
