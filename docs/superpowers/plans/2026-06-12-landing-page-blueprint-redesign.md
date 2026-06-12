# Landing Page "Blueprint Minimal" Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `docs/index.html` with a blue-white engineering-drawing
minimal page featuring two interactive matter.js physics scenes (six-cable
parallel robot hero; offset-tower stability lab), per the approved spec
`docs/superpowers/specs/2026-06-12-landing-page-blueprint-redesign-design.md`.

**Architecture:** One hand-written static HTML file + three vendored/local
JS assets (no build step). Both scenes share one vendored matter.js runtime,
lazy-initialized per scene via IntersectionObserver, with static SVG
fallbacks for reduced-motion/coarse-pointer. A repo unittest pins the page's
numeric claims to the README so the site can never drift again.

**Tech Stack:** vanilla HTML/CSS/JS, matter.js 0.20.0 (vendored), Python
unittest for content-parity tests, `sips` for image downscaling, pygame for
the social-card generator.

**Working directory:** `/Users/kingcode/Documents/Newton/newton-vla-demo`
(branch `demo-live-export`). All test commands run from the repo root.

**Design tokens (used throughout — do not improvise):**
blue `#1d4ed8` · ink `#0f1a2e` · grey text `#5a6678` / `#8a94a6` ·
hairline `#e3e8f0` · amber `#e8a23d` · grid `rgba(29,78,216,.05)` ·
radius 3px · fonts: Inter (headings, via system fallback stack),
IBM Plex Mono → `ui-monospace` stack (data).

---

### Task 1: Anti-drift content test (failing first)

**Files:**
- Test: `demo_live/tests/test_docs_site.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Pins docs/index.html (the GitHub Pages landing site) to the repo's
ground truth so the site can never silently drift from the README again,
and enforces the redesign's hard constraints (no lab affiliation text,
JS weight budget, scenes present with static fallbacks)."""

from __future__ import annotations

import gzip
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class DocsSiteParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(DOCS / "index.html")
        cls.readme = _read(ROOT / "README.md")

    def test_test_count_matches_readme_badge(self):
        badge = re.search(r"tests-(\d+)%20passing", self.readme)
        self.assertIsNotNone(badge, "README test badge missing")
        self.assertIn(f">{badge.group(1)}<", self.html,
                      "landing page test count must equal README badge")

    def test_version_matches_package(self):
        from demo_live import __version__
        self.assertIn(f"REV {__version__}", self.html)

    def test_line_count_matches_readme_badge(self):
        badge = re.search(r"code-(\d+)%20lines", self.readme)
        self.assertIsNotNone(badge)
        self.assertIn(badge.group(1), self.html)

    def test_no_lab_affiliation_anywhere(self):
        for needle in ("Xidian", "State Key", "Electromechanical Integrated",
                       "重点实验室", "西安电子"):
            self.assertNotIn(needle, self.html,
                             f"affiliation text {needle!r} must not appear")

    def test_blueprint_chapter_markers_present(self):
        for sht in ("SHT 01", "SHT 02", "SHT 03", "SHT 04", "SHT 05"):
            self.assertIn(sht, self.html)

    def test_scene_canvases_and_fallbacks_present(self):
        for scene_id in ("hero-scene", "lab-scene"):
            self.assertIn(f'id="{scene_id}"', self.html)
            self.assertIn(f'id="{scene_id}-fallback"', self.html)

    def test_reduced_motion_media_query_present(self):
        self.assertIn("prefers-reduced-motion", self.html)


class DocsSiteAssetBudgetTest(unittest.TestCase):
    def test_js_bundle_under_100kb_gzip(self):
        total = 0
        for name in ("matter.min.js", "hero.js", "lab.js"):
            p = DOCS / "assets" / name
            self.assertTrue(p.exists(), f"missing docs/assets/{name}")
            total += len(gzip.compress(p.read_bytes()))
        self.assertLess(total, 100 * 1024,
                        f"JS budget exceeded: {total / 1024:.0f} KB gzip")

    def test_experiment_figures_present_and_small(self):
        for name in ("experiment_aligned.png", "experiment_offset.png",
                     "experiment_topple.png"):
            p = DOCS / "figures" / name
            self.assertTrue(p.exists(), f"missing docs/figures/{name}")
            self.assertLess(p.stat().st_size, 350 * 1024,
                            f"{name} over 350 KB; downscale it")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --extra demo python -m unittest demo_live.tests.test_docs_site -v`
Expected: FAIL — current index.html lacks `SHT 01`, `REV 0.2.0` etc.;
assets missing. (test_no_lab_affiliation passes — fine.)

- [ ] **Step 3: Commit the red test**

```bash
git add demo_live/tests/test_docs_site.py
git commit -m "test: pin landing page to repo ground truth (red)"
```

---

### Task 2: Vendor matter.js

**Files:**
- Create: `docs/assets/matter.min.js`

- [ ] **Step 1: Download pinned version**

```bash
mkdir -p docs/assets
curl -fsSL https://cdn.jsdelivr.net/npm/matter-js@0.20.0/build/matter.min.js \
  -o docs/assets/matter.min.js
grep -o "0.20.0" docs/assets/matter.min.js | head -1   # expect: 0.20.0
```

- [ ] **Step 2: Commit**

```bash
git add docs/assets/matter.min.js
git commit -m "build: vendor matter.js 0.20.0 for the landing page scenes"
```

---

### Task 3: New index.html (complete rewrite, static content first)

**Files:**
- Modify: `docs/index.html` (full replacement)

The page is complete and meaningful WITHOUT JavaScript: every scene has a
static SVG fallback shown by default; JS upgrades it. Keep ALL `<meta>` OG
tags from the old file head, update description. The full file is written
in one shot; scenes' `<canvas>` elements start hidden.

- [ ] **Step 1: Write the new file** — full content below. Note the
structure; numbers MUST match README (238 tests / 7730 lines / 0.2.0 /
perf table values).

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Newton VLA Live Demo — Embodied AI on a MacBook</title>
<meta name="description" content="A 3-minute classroom demo of embodied AI on a MacBook — real XPBD physics, Claude as the VLA brain, 60 fps CPU-only. Drawn like an engineering sheet, driven by real physics.">
<meta property="og:title" content="Newton VLA Live Demo">
<meta property="og:description" content="Embodied AI on a MacBook — no GPU, no cloud. Newton XPBD + pygame + Claude.">
<meta property="og:image" content="figures/social_preview.png">
<meta property="og:url" content="https://hollis36.github.io/newton-vla-demo/">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Newton VLA Live Demo">
<meta name="twitter:description" content="Embodied AI on a MacBook — no GPU, no cloud.">
<meta name="twitter:image" content="figures/social_preview.png">
<style>
:root{
  --blue:#1d4ed8; --ink:#0f1a2e; --t2:#5a6678; --t3:#8a94a6;
  --rule:#e3e8f0; --amber:#e8a23d; --grid:rgba(29,78,216,.05);
  --mono:ui-monospace,"IBM Plex Mono","SF Mono",SFMono-Regular,Menlo,monospace;
  --sans:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:#fff;color:var(--ink);font-family:var(--sans);
  line-height:1.65;-webkit-font-smoothing:antialiased;font-size:15px}
a{color:var(--blue);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1060px;margin:0 auto;padding:0 28px}
.mono{font-family:var(--mono)}
/* header */
header{border-bottom:1px solid var(--blue)}
.hd{display:flex;justify-content:space-between;align-items:center;padding:14px 0}
.hd .mark{font-family:var(--mono);font-size:12px;letter-spacing:.14em;color:var(--blue)}
.hd .meta{font-family:var(--mono);font-size:10px;color:var(--t3);text-align:right}
/* chapter labels */
.sht{font-family:var(--mono);font-size:11px;letter-spacing:.16em;
  color:var(--blue);margin:0 0 18px}
.sht .n{color:var(--t3)}
section{padding:72px 0 8px}
section+section{border-top:1px solid var(--rule);margin-top:64px}
/* hero */
.hero{position:relative;
  background:
    repeating-linear-gradient(0deg,transparent 0 47px,var(--grid) 47px 48px),
    repeating-linear-gradient(90deg,transparent 0 47px,var(--grid) 47px 48px),#fff;
  border-bottom:1px solid var(--rule)}
.hero-grid{display:grid;grid-template-columns:1.05fr 1fr;gap:40px;
  align-items:center;padding:64px 0 56px}
h1{margin:0 0 18px;font-size:clamp(40px,5.4vw,64px);font-weight:450;
  letter-spacing:-.02em;line-height:1.04}
h1 .dot{color:var(--blue)}
.tagline{max-width:420px;color:var(--t2);font-size:15.5px;margin:0 0 26px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.2em;
  color:var(--blue);margin-bottom:18px}
.cta{display:flex;gap:12px;flex-wrap:wrap}
.btn{font-family:var(--mono);font-size:13px;padding:10px 20px;border-radius:3px}
.btn-solid{background:var(--blue);color:#fff}
.btn-solid:hover{background:#1742ac;text-decoration:none}
.btn-line{border:1px solid var(--blue);color:var(--blue)}
.btn-line:hover{background:rgba(29,78,216,.05);text-decoration:none}
/* scenes */
.scene{position:relative}
.scene canvas{display:none;width:100%;height:auto;cursor:grab}
.scene canvas:active{cursor:grabbing}
.scene.live canvas{display:block}
.scene.live .fallback{display:none}
.scene .hint{display:flex;justify-content:space-between;margin-top:6px;
  font-family:var(--mono);font-size:10px;color:var(--t3)}
.scene .hint button{all:unset;cursor:pointer;color:var(--blue);
  font-family:var(--mono);font-size:10px}
/* spec row */
.specs{display:grid;grid-template-columns:repeat(4,1fr);gap:0;padding:26px 0}
.spec{padding:2px 0 2px 16px;border-left:1px solid var(--rule)}
.spec:first-child{border-left:2px solid var(--blue)}
.spec b{display:block;font-family:var(--mono);font-weight:400;
  font-size:24px;color:var(--ink)}
.spec b small{font-size:12px;color:var(--t3)}
.spec span{font-size:11.5px;color:var(--t3)}
/* control loop */
.loop{border:1px solid var(--rule);border-radius:3px;padding:26px;overflow-x:auto}
.loop svg{display:block;min-width:640px;width:100%}
/* figures */
.figgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
figure{margin:0}
figure .frame{border:1px solid var(--ink);border-radius:2px;overflow:hidden}
figure img,figure video{display:block;width:100%;height:auto}
figcaption{font-family:var(--mono);font-size:10px;color:var(--t3);
  margin-top:8px;line-height:1.5}
figcaption b{color:var(--ink);font-weight:400}
.filmfig{margin-top:26px}
/* lab scene */
.labwrap{display:grid;grid-template-columns:1.25fr 1fr;gap:36px;align-items:start}
.lab-controls{display:flex;gap:8px;margin:0 0 14px}
.lab-controls button{all:unset;cursor:pointer;font-family:var(--mono);
  font-size:12px;padding:7px 14px;border:1px solid var(--rule);
  border-radius:3px;color:var(--t2)}
.lab-controls button.on{border-color:var(--blue);color:var(--blue)}
.theory{border-left:2px solid var(--blue);padding:4px 0 4px 16px;
  font-size:13.5px;color:var(--t2)}
.theory .mono{color:var(--ink)}
/* tables */
table{border-collapse:collapse;width:100%;font-size:13px}
th{font-family:var(--mono);font-size:10px;letter-spacing:.1em;color:var(--t3);
  font-weight:400;text-align:left;padding:8px 12px;border-bottom:1px solid var(--ink)}
td{padding:7px 12px;border-bottom:1px solid var(--rule);color:var(--t2)}
td.mono,th.r,td.r{font-family:var(--mono)}
td:first-child{color:var(--ink)}
.r{text-align:right}
.tables{display:grid;grid-template-columns:1fr 1fr;gap:40px}
/* footer title block */
footer{margin-top:88px;border-top:1.5px solid var(--ink)}
.tb{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;border-left:1px solid var(--rule)}
.tb>div{border-right:1px solid var(--rule);padding:14px 16px}
.tb .k{font-family:var(--mono);font-size:9px;letter-spacing:.12em;
  color:var(--t3);display:block;margin-bottom:4px}
.tb .v{font-size:13px;color:var(--ink)}
.tb a{font-size:13px;display:block}
.foot-note{font-family:var(--mono);font-size:10px;color:var(--t3);
  padding:14px 0 28px}
/* motion */
.fade{opacity:0;transform:translateY(12px);
  transition:opacity .24s ease,transform .24s ease}
.fade.in{opacity:1;transform:none}
@media (prefers-reduced-motion: reduce){
  .fade{opacity:1;transform:none;transition:none}
  html{scroll-behavior:auto}
}
@media (max-width:860px){
  .hero-grid,.labwrap,.tables{grid-template-columns:1fr}
  .specs{grid-template-columns:1fr 1fr;row-gap:22px}
  .figgrid{grid-template-columns:1fr}
}
</style>
</head>
<body>

<header>
  <div class="wrap hd">
    <span class="mark">NEWTON · VLA — LIVE DEMO</span>
    <span class="meta">DOC NO. NVD-2026 · REV 0.2.0 · SHT 01/05<br>
      EMBODIED AI · CLASSROOM SCALE</span>
  </div>
</header>

<!-- ============================== SHT 01 · HERO -->
<div class="hero">
  <div class="wrap hero-grid">
    <div>
      <div class="eyebrow">SHT 01 <span style="color:var(--t3)">/05</span> — EMBODIED AI ON A MACBOOK</div>
      <h1>Real physics.<br>Real language.<br>One laptop<span class="dot">.</span></h1>
      <p class="tagline">A 3-minute classroom demo of embodied AI:
        Newton XPBD rigid-body physics, Claude as the vision-language-action
        brain, 60 fps CPU-only. No GPU, no cloud.</p>
      <div class="cta">
        <a class="btn btn-solid" href="figures/demo_rehearsal.mp4">▶&nbsp; Demo film · 52 s</a>
        <a class="btn btn-line" href="https://github.com/Hollis36/newton-vla-demo">GitHub ↗</a>
      </div>
    </div>
    <div class="scene" id="hero-scene-box">
      <canvas id="hero-scene" width="560" height="420" aria-label="Interactive six-cable parallel robot: drag the suspended cabin"></canvas>
      <div class="fallback" id="hero-scene-fallback"><!-- static line art -->
        <svg viewBox="0 0 560 420" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Six-cable suspended cabin over a parabolic reflector, drawn as a line schematic">
          <g stroke="#0f1a2e" stroke-width="1.3" fill="none">
            <path d="M50 360 L65 70 L80 360 M55 290 L75 290 M59 230 L71 230 M62 160 L68 160"/>
            <path d="M480 360 L495 70 L510 360 M485 290 L505 290 M489 230 L501 230 M492 160 L498 160"/>
            <path d="M262 372 L272 40 L282 372 M266 300 L278 300 M268 230 L276 230 M270 140 L274 140" opacity=".35"/>
          </g>
          <g stroke="#1d4ed8" stroke-width=".9" fill="none">
            <path d="M65 72 Q 180 160 244 218"/><path d="M65 76 Q 185 175 246 230"/>
            <path d="M495 72 Q 380 160 316 218"/><path d="M495 76 Q 375 175 314 230"/>
            <path d="M272 42 Q 277 130 279 205" opacity=".55"/>
            <path d="M272 42 Q 283 130 285 205" opacity=".55"/>
          </g>
          <g transform="translate(280 235)">
            <polygon points="-40,-13 -20,-28 20,-28 40,-13 20,17 -20,17"
              fill="rgba(29,78,216,.05)" stroke="#1d4ed8" stroke-width="1.4"/>
            <line x1="-9" y1="0" x2="9" y2="0" stroke="#1d4ed8"/>
            <line x1="0" y1="-9" x2="0" y2="9" stroke="#1d4ed8"/>
            <circle r="5.5" fill="none" stroke="#1d4ed8"/>
          </g>
          <path d="M60 392 Q 280 318 500 392" stroke="#0f1a2e" stroke-width="1.2" fill="none"/>
          <text x="280" y="412" font-family="monospace" font-size="10" fill="#8a94a6" text-anchor="middle">cable-driven parallel robot · static view</text>
        </svg>
      </div>
      <div class="hint">
        <span id="hero-readout">drag the cabin ⌖ · six-cable suspension</span>
        <button id="hero-reset" type="button">reset ⟳</button>
      </div>
    </div>
  </div>
</div>

<!-- spec row -->
<div class="wrap">
  <div class="specs fade">
    <div class="spec"><b data-count="238">238</b><span>tests · 100 % passing</span></div>
    <div class="spec"><b data-count="60">60 <small>fps</small></b><span>Apple Silicon, CPU-only</span></div>
    <div class="spec"><b>0.3 <small>ms</small></b><span>physics step · 39× faster</span></div>
    <div class="spec"><b>1 <small>ms</small></b><span>command → first motion</span></div>
  </div>
</div>

<!-- ============================== SHT 02 · CONTROL LOOP -->
<section class="wrap fade">
  <p class="sht">SHT 02 <span class="n">/05</span> — CONTROL LOOP · FEEDFORWARD + SLOW FEEDBACK</p>
  <div class="loop">
    <svg id="loop-svg" viewBox="0 0 880 170" xmlns="http://www.w3.org/2000/svg" role="img"
      aria-label="Control block diagram: voice or text input feeds a 1 millisecond keyword feedforward that drives the arm immediately, while Claude reviews in a 9.4 second slow feedback branch">
      <g font-family="ui-monospace,monospace" font-size="12">
        <rect x="10" y="58" width="120" height="44" fill="none" stroke="#0f1a2e" stroke-width="1.2" rx="2"/>
        <text x="70" y="84" text-anchor="middle" fill="#0f1a2e">voice / text</text>
        <path class="draw" d="M130 80 H 200" stroke="#1d4ed8" stroke-width="1.4" fill="none" marker-end="url(#arr)"/>
        <rect x="200" y="50" width="150" height="60" fill="rgba(29,78,216,.04)" stroke="#1d4ed8" stroke-width="1.4" rx="2"/>
        <text x="275" y="76" text-anchor="middle" fill="#1d4ed8">keyword FF</text>
        <text x="275" y="96" text-anchor="middle" fill="#8a94a6" font-size="10">~1 ms · deterministic</text>
        <path class="draw" d="M350 80 H 430" stroke="#1d4ed8" stroke-width="1.4" fill="none" marker-end="url(#arr)"/>
        <rect x="430" y="50" width="160" height="60" fill="none" stroke="#0f1a2e" stroke-width="1.2" rx="2"/>
        <text x="510" y="76" text-anchor="middle" fill="#0f1a2e">3-DOF arm</text>
        <text x="510" y="96" text-anchor="middle" fill="#8a94a6" font-size="10">min-jerk + PD</text>
        <path class="draw" d="M590 80 H 660" stroke="#0f1a2e" stroke-width="1.2" fill="none" marker-end="url(#arrk)"/>
        <rect x="660" y="58" width="120" height="44" fill="none" stroke="#0f1a2e" stroke-width="1.2" rx="2"/>
        <text x="720" y="84" text-anchor="middle" fill="#0f1a2e">stage</text>
        <path class="draw" d="M70 102 V 150 H 480" stroke="#8a94a6" stroke-width="1.1"
          stroke-dasharray="5 4" fill="none"/>
        <rect x="480" y="128" width="180" height="42" fill="none" stroke="#8a94a6"
          stroke-width="1.1" stroke-dasharray="5 4" rx="2"/>
        <text x="570" y="146" text-anchor="middle" fill="#5a6678">Claude review</text>
        <text x="570" y="162" text-anchor="middle" fill="#8a94a6" font-size="10">~9.4 s · reconciles / confirms</text>
        <path class="draw" d="M660 149 H 730 V 102" stroke="#8a94a6" stroke-width="1.1"
          stroke-dasharray="5 4" fill="none" marker-end="url(#arrg)"/>
      </g>
      <defs>
        <marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="#1d4ed8"/></marker>
        <marker id="arrk" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="#0f1a2e"/></marker>
        <marker id="arrg" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="#8a94a6"/></marker>
      </defs>
    </svg>
  </div>
  <p style="font-size:13.5px;color:var(--t2);max-width:680px">A foundation
    model takes seconds; a 60 fps stage gives you 16.7 ms. The demo decouples
    them: a deterministic keyword feedforward starts the arm in ~1 ms, Claude
    returns later as a slow feedback branch and reconciles — a generation
    counter keeps stale results from clobbering newer commands. The audience
    perceives instant response with intelligent backfill.</p>
</section>

<!-- ============================== SHT 03 · THREE MODES -->
<section class="wrap fade">
  <p class="sht">SHT 03 <span class="n">/05</span> — THREE INTERACTION MODES</p>
  <div class="figgrid">
    <figure>
      <div class="frame"><img src="figures/catch_industrial.png" alt="Ball-catch mode: trajectory sampling and intercept ring" loading="lazy"></div>
      <figcaption><b>FIG. 3-1</b> — Ball catch · closed-form MPC intercept · 62–82 % measured</figcaption>
    </figure>
    <figure>
      <div class="frame"><img src="figures/stack_industrial.png" alt="Talk-to-arm mode: natural language tower stacking" loading="lazy"></div>
      <figcaption><b>FIG. 3-2</b> — Talk to arm · natural language → JSON action → motion in 1 ms</figcaption>
    </figure>
    <figure>
      <div class="frame"><img src="figures/experiment_topple.png" alt="Stability lecture mode: offset tower toppling under real physics" loading="lazy"></div>
      <figcaption><b>FIG. 3-3</b> — Stability lecture · offset tower topples under real XPBD</figcaption>
    </figure>
  </div>
  <figure class="filmfig">
    <div class="frame">
      <video controls preload="metadata" poster="figures/vla_panel_industrial.png">
        <source src="figures/demo_rehearsal.mp4" type="video/mp4">
        <img src="figures/showcase.gif" alt="Newton VLA demo rehearsal">
      </video>
    </div>
    <figcaption><b>FIG. 3-4</b> — 52 s auto-recorded rehearsal: catch · drive · pick · stack · voice, dual-arm in parallel</figcaption>
  </figure>
</section>

<!-- ============================== SHT 04 · STABILITY LAB -->
<section class="wrap fade">
  <p class="sht">SHT 04 <span class="n">/05</span> — STABILITY LAB · CENTER OF MASS vs SUPPORT</p>
  <div class="labwrap">
    <div class="scene" id="lab-scene-box">
      <canvas id="lab-scene" width="560" height="360" aria-label="Interactive tower: choose a per-layer offset and watch the center of mass criterion decide stability"></canvas>
      <div class="fallback" id="lab-scene-fallback">
        <svg viewBox="0 0 560 360" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Three stacked blocks with offset layers, a dashed center-of-mass plumb line, and a support bracket on the ground">
          <line x1="296" y1="36" x2="296" y2="330" stroke="#1d4ed8" stroke-dasharray="4 6"/>
          <text x="296" y="26" font-family="monospace" font-size="10" fill="#1d4ed8" text-anchor="middle">⌖ CoM</text>
          <rect x="250" y="246" width="84" height="84" fill="#fff" stroke="#0f1a2e" stroke-width="1.3"/>
          <rect x="266" y="162" width="84" height="84" fill="#fff" stroke="#0f1a2e" stroke-width="1.3"/>
          <rect x="282" y="78" width="84" height="84" fill="rgba(29,78,216,.05)" stroke="#1d4ed8" stroke-width="1.3"/>
          <line x1="120" y1="331" x2="520" y2="331" stroke="#0f1a2e" stroke-width="1.3"/>
          <path d="M250 342 H334 M250 337 V347 M334 337 V347" stroke="#1d4ed8" stroke-width="1.5" fill="none"/>
          <text x="292" y="356" font-family="monospace" font-size="9" fill="#8a94a6" text-anchor="middle">support base</text>
        </svg>
      </div>
      <div class="hint">
        <span id="lab-readout">d = 40 mm · CoM inside base · STABLE</span>
        <button id="lab-reset" type="button">reset ⟳</button>
      </div>
    </div>
    <div>
      <div class="lab-controls" role="group" aria-label="per-layer offset">
        <button data-d="0" type="button">d = 0</button>
        <button data-d="40" class="on" type="button">d = 40 mm</button>
        <button data-d="90" type="button">d = 90 mm</button>
      </div>
      <p class="theory">Equal cubes of height <span class="mono">h = 200 mm</span>:
        the top two layers' combined center of mass sits
        <span class="mono">1.5 d</span> off the bottom block, so the tower
        must topple once <span class="mono">d &gt; h/3 ≈ 67 mm</span>.
        40 survives. 90 falls. The verdict here — like in the demo itself —
        is computed by the physics engine, not scripted.</p>
      <p style="font-size:13.5px;color:var(--t2)">In the live demo
        (<span class="mono">make experiment</span>) the right arm runs this
        same lecture with real rigid bodies: stack at 0 → 4 → 9 cm per
        layer, settle, verdict, tidy up, repeat. A regression test pins the
        4-vs-9 cm bracket against the XPBD solver so the climax can never
        silently break.</p>
    </div>
  </div>
</section>

<!-- ============================== SHT 05 · ARCHITECTURE -->
<section class="wrap fade">
  <p class="sht">SHT 05 <span class="n">/05</span> — ARCHITECTURE · 7730 LINES, 238 TESTS</p>
  <div class="tables">
    <div>
      <table aria-label="module overview">
        <thead><tr><th>MODULE</th><th>ROLE</th><th class="r">LINES</th></tr></thead>
        <tbody>
          <tr><td>__main__.py</td><td>pygame loop · events · dispatch</td><td class="r mono">1358</td></tr>
          <tr><td>physics.py</td><td>Newton world · real-blocks grasp</td><td class="r mono">660</td></tr>
          <tr><td>vla.py</td><td>Claude CLI · keyword fallback</td><td class="r mono">467</td></tr>
          <tr><td>tasks.py</td><td>pick / place / stack / gestures</td><td class="r mono">432</td></tr>
          <tr><td>catcher.py</td><td>MPC ballistic intercept</td><td class="r mono">271</td></tr>
          <tr><td>experiment.py</td><td>stability lecture coordinator</td><td class="r mono">194</td></tr>
          <tr><td>collab.py</td><td>two-arm relay coordinator</td><td class="r mono">167</td></tr>
        </tbody>
      </table>
      <p style="font-size:12px;color:var(--t3)">+ scene/ renderers, voice,
        telemetry, effects… <a href="https://github.com/Hollis36/newton-vla-demo#architecture">full table ↗</a></p>
    </div>
    <div>
      <table aria-label="measured performance">
        <thead><tr><th>SCENARIO</th><th class="r">AVG FPS</th><th class="r">SAMPLES</th></tr></thead>
        <tbody>
          <tr><td>IDLE 20 s</td><td class="r mono">60.7</td><td class="r mono">1211</td></tr>
          <tr><td>Scripted catch</td><td class="r mono">59.6</td><td class="r mono">594</td></tr>
          <tr><td>Scripted VLA + real blocks</td><td class="r mono">56.9</td><td class="r mono">1132</td></tr>
          <tr><td>Collab relay 90 s</td><td class="r mono">55.0</td><td class="r mono">4918</td></tr>
          <tr><td>Collab + real blocks 90 s</td><td class="r mono">56.8</td><td class="r mono">5090</td></tr>
        </tbody>
      </table>
      <p style="font-size:12px;color:var(--t3)">Apple Silicon, CPU-only ·
        physics 0.3 ms/frame teleport · ~5 ms real-blocks</p>
    </div>
  </div>
</section>

<!-- ============================== FOOTER · TITLE BLOCK -->
<footer>
  <div class="wrap">
    <div class="tb">
      <div><span class="k">PROJECT</span>
        <span class="v">Newton VLA Live Demo — embodied AI on a MacBook</span></div>
      <div><span class="k">DRAWN</span><span class="v">Hollis36</span>
        <span class="k" style="margin-top:8px">REV / DATE</span>
        <span class="v mono" style="font-size:11px">0.2.0 · 2026-06</span></div>
      <div><span class="k">DOCUMENTS</span>
        <a href="report.pdf">Design report · 18 p</a>
        <a href="slides.pdf">Slides · 24 p</a></div>
      <div><span class="k">SOURCE</span>
        <a href="https://github.com/Hollis36/newton-vla-demo">GitHub ↗</a>
        <a href="https://github.com/Hollis36/newton-vla-demo/blob/main/demo_live/REHEARSAL.md">Rehearsal script</a></div>
    </div>
    <p class="foot-note">MIT · built on a MacBook · no cloud · no GPU ·
      powered by Newton, Claude, and a lot of min-jerk curves</p>
  </div>
</footer>

<script src="assets/matter.min.js" defer></script>
<script src="assets/hero.js" defer></script>
<script src="assets/lab.js" defer></script>
<script>
// Motion budget item 1+3: section fade-up & one-shot countup (reduced-motion safe).
(function(){
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var io = new IntersectionObserver(function(es){
    es.forEach(function(e){
      if (!e.isIntersecting) return;
      e.target.classList.add('in');
      e.target.querySelectorAll('[data-count]').forEach(function(el){
        var to = +el.dataset.count, t0 = performance.now(), suffix = el.querySelector('small');
        function tick(t){
          var p = Math.min(1, (t - t0) / 700);
          el.childNodes[0].nodeValue = Math.round(to * (p * (2 - p))) + (suffix ? ' ' : '');
          if (p < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
        delete el.dataset.count;
      });
      io.unobserve(e.target);
    });
  }, {threshold: 0.18});
  document.querySelectorAll('.fade').forEach(function(s){ io.observe(s); });
  // Motion budget item 2: control-loop strokes draw in once.
  var svg = document.getElementById('loop-svg');
  if (svg) {
    svg.querySelectorAll('.draw').forEach(function(p){
      var L = p.getTotalLength();
      p.style.strokeDasharray = p.getAttribute('stroke-dasharray') || L;
      p.style.strokeDashoffset = L;
    });
    new IntersectionObserver(function(es, o){
      if (!es[0].isIntersecting) return;
      svg.querySelectorAll('.draw').forEach(function(p, i){
        p.style.transition = 'stroke-dashoffset .5s ease ' + (i * 0.12) + 's';
        p.style.strokeDashoffset = '0';
      });
      o.disconnect();
    }, {threshold: 0.4}).observe(svg);
  }
})();
</script>
</body>
</html>
```

- [ ] **Step 2: Sanity-serve and eyeball the static page**

```bash
python3 -m http.server 8011 -d docs &
sleep 1 && curl -s localhost:8011 | grep -c "SHT 0"   # expect ≥ 5
```
Open `http://localhost:8011` in a browser: static fallbacks visible in both
scene slots; header/footer title blocks correct; no console errors except
hero.js/lab.js 404 (not written yet).

- [ ] **Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat(site): blueprint-minimal rewrite of the landing page (static layer)"
```

---

### Task 4: hero.js — six-cable parallel robot scene

**Files:**
- Create: `docs/assets/hero.js`

- [ ] **Step 1: Write the scene** (complete file):

```javascript
/* Six-cable parallel robot hero scene — line-art matter.js miniature.
   Cabin hangs from 6 cables (3 anchor points × 2 attach points); drag it,
   watch tensions; a "GAIN" meter maps cabin deviation to dB loss
   (structure → electromagnetic performance). Sleeps when settled. */
(function () {
  'use strict';
  var box = document.getElementById('hero-scene-box');
  var canvas = document.getElementById('hero-scene');
  if (!box || !canvas || !window.Matter) return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (matchMedia('(pointer: coarse)').matches && innerWidth < 700) return;

  var M = Matter, W = 560, H = 420;
  var BLUE = '#1d4ed8', INK = '#0f1a2e', GREY = '#8a94a6', AMBER = '#e8a23d';
  var engine, cabin, cables, mouseC, raf = null, settledAt = 0;
  var TARGET = { x: 300, y: 252 };
  var ANCHORS = [{ x: 65, y: 72 }, { x: 272, y: 42 }, { x: 495, y: 72 }];

  function build() {
    engine = M.Engine.create({ gravity: { x: 0, y: 1, scale: 0.0008 } });
    cabin = M.Bodies.polygon(280, 235, 6, 34, {
      frictionAir: 0.03, density: 0.004, angle: Math.PI / 6,
    });
    cables = ANCHORS.flatMap(function (a, i) {
      return [-12, 12].map(function (dx) {
        return M.Constraint.create({
          pointA: a, bodyB: cabin, pointB: { x: dx, y: -14 },
          stiffness: 0.05, damping: 0.08,
          length: Math.hypot(a.x - (280 + dx), a.y - 221) * 0.99,
        });
      });
    });
    var mouse = M.Mouse.create(canvas);
    // matter reads CSS pixels; canvas is responsive — fix the scale.
    function syncMouse() {
      var r = canvas.getBoundingClientRect();
      M.Mouse.setScale(mouse, { x: W / r.width, y: H / r.height });
    }
    syncMouse(); addEventListener('resize', syncMouse);
    mouseC = M.MouseConstraint.create(engine, {
      mouse: mouse, constraint: { stiffness: 0.08, damping: 0.1 },
    });
    M.Composite.add(engine.world, [cabin].concat(cables, [mouseC]));
    canvas.addEventListener('pointerdown', wake);
  }

  function tension(c) {
    var dx = c.pointA.x - (c.bodyB.position.x + c.pointB.x),
        dy = c.pointA.y - (c.bodyB.position.y + c.pointB.y);
    return Math.max(0, Math.hypot(dx, dy) - c.length);
  }

  function draw() {
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    ctx.lineJoin = 'round'; ctx.font = '10px ui-monospace, monospace';
    // towers (static decoration)
    ctx.strokeStyle = INK; ctx.lineWidth = 1.3;
    [[50, 65, 80], [480, 495, 510]].forEach(function (t) {
      ctx.beginPath();
      ctx.moveTo(t[0], 360); ctx.lineTo(t[1], 70); ctx.lineTo(t[2], 360);
      [290, 230, 160].forEach(function (y, i) {
        ctx.moveTo(t[1] - 10 + i * 3, y); ctx.lineTo(t[1] + 10 - i * 3, y);
      });
      ctx.stroke();
    });
    ctx.globalAlpha = 0.35;
    ctx.beginPath(); ctx.moveTo(262, 372); ctx.lineTo(272, 40); ctx.lineTo(282, 372); ctx.stroke();
    ctx.globalAlpha = 1;
    // dish
    ctx.lineWidth = 1.2; ctx.beginPath();
    ctx.moveTo(60, 392); ctx.quadraticCurveTo(280, 318, 500, 392); ctx.stroke();
    // cables — width maps to tension
    var tens = cables.map(tension), tMax = Math.max.apply(null, tens) || 1;
    cables.forEach(function (c, i) {
      var p = M.Constraint.pointBWorld(c);
      ctx.strokeStyle = BLUE; ctx.lineWidth = 0.7 + 1.6 * (tens[i] / tMax);
      ctx.globalAlpha = i >= 2 && i < 4 ? 0.55 : 1;   // center pair behind
      ctx.beginPath(); ctx.moveTo(c.pointA.x, c.pointA.y); ctx.lineTo(p.x, p.y); ctx.stroke();
      ctx.globalAlpha = 1;
    });
    ctx.fillStyle = BLUE;
    ctx.fillText('T₁ ' + (380 + tens[0] * 14 | 0) + ' N', 150, 105);
    ctx.fillStyle = GREY;
    ctx.fillText('T₂ ' + (380 + tens[4] * 14 | 0) + ' N', 360, 105);
    // cabin
    ctx.strokeStyle = BLUE; ctx.lineWidth = 1.4;
    ctx.fillStyle = 'rgba(29,78,216,.05)';
    ctx.beginPath();
    cabin.vertices.forEach(function (v, i) { i ? ctx.lineTo(v.x, v.y) : ctx.moveTo(v.x, v.y); });
    ctx.closePath(); ctx.fill(); ctx.stroke();
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cabin.position.x - 9, cabin.position.y); ctx.lineTo(cabin.position.x + 9, cabin.position.y);
    ctx.moveTo(cabin.position.x, cabin.position.y - 9); ctx.lineTo(cabin.position.x, cabin.position.y + 9);
    ctx.stroke();
    // Stewart-platform hint: three short struts under the cabin (decoration,
    // rotates with the body via its lower vertices).
    ctx.strokeStyle = INK; ctx.lineWidth = 0.9;
    var vb = cabin.vertices;
    ctx.beginPath();
    ctx.moveTo(vb[3].x, vb[3].y); ctx.lineTo(cabin.position.x - 10, cabin.position.y + 46);
    ctx.moveTo(vb[4].x, vb[4].y); ctx.lineTo(cabin.position.x + 10, cabin.position.y + 46);
    ctx.moveTo(cabin.position.x - 10, cabin.position.y + 46);
    ctx.lineTo(cabin.position.x + 10, cabin.position.y + 46);
    ctx.stroke();
    // target + deviation
    var dev = Math.hypot(cabin.position.x - TARGET.x, cabin.position.y - TARGET.y);
    var mm = dev * 2.4;  // page scale: ≈2.4 mm per px (toy units)
    ctx.strokeStyle = AMBER;
    ctx.beginPath(); ctx.arc(TARGET.x, TARGET.y, 3.5, 0, 7); ctx.stroke();
    if (dev > 6) {
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(cabin.position.x, cabin.position.y);
      ctx.lineTo(TARGET.x, TARGET.y); ctx.stroke(); ctx.setLineDash([]);
    }
    // gain meter (electromechanical coupling)
    var loss = Math.min(3, mm / 80);
    ctx.strokeStyle = '#e3e8f0'; ctx.strokeRect(420, 140, 110, 46);
    ctx.fillStyle = GREY; ctx.fillText('GAIN  (structure→EM)', 428, 156);
    ctx.strokeRect(428, 162, 94, 6);
    ctx.fillStyle = loss > 1.5 ? AMBER : BLUE;
    ctx.fillRect(428, 162, 94 * (1 - loss / 3), 6);
    ctx.fillText('−' + loss.toFixed(1) + ' dB', 428, 182);
    var read = document.getElementById('hero-readout');
    if (read) read.textContent =
      'Δ ' + mm.toFixed(0) + ' mm · gain −' + loss.toFixed(1) + ' dB' +
      (loss > 1.5 ? ' · REPOINT' : ' · ON TARGET');
  }

  function step(t) {
    M.Engine.update(engine, 1000 / 60);
    draw();
    var moving = cabin.speed > 0.06 || (mouseC.body !== null);
    if (moving) settledAt = t;
    raf = (t - settledAt < 2200) ? requestAnimationFrame(step) : null;
  }
  function wake() { if (!raf) { settledAt = performance.now(); raf = requestAnimationFrame(step); } }

  build();
  box.classList.add('live');
  document.getElementById('hero-reset').addEventListener('click', function () {
    M.Body.setPosition(cabin, { x: 280, y: 235 });
    M.Body.setVelocity(cabin, { x: 0, y: 0 });
    M.Body.setAngularVelocity(cabin, 0);
    wake();
  });
  new IntersectionObserver(function (es) {
    es[0].isIntersecting ? wake() : (raf && cancelAnimationFrame(raf), raf = null);
  }, { threshold: 0.1 }).observe(canvas);
})();
```

- [ ] **Step 2: Verify in browser**

Reload `http://localhost:8011`. Expect: canvas replaces the static SVG;
cabin hangs and sways briefly, then the scene goes idle (CPU near 0 — check
in the browser task manager); dragging the cabin re-tensions cables, Δ and
GAIN readouts move; `reset ⟳` recenters. No console errors.

- [ ] **Step 3: Commit**

```bash
git add docs/assets/hero.js
git commit -m "feat(site): interactive six-cable parallel robot hero scene"
```

---

### Task 5: lab.js — offset-tower stability scene

**Files:**
- Create: `docs/assets/lab.js`

- [ ] **Step 1: Write the scene** (complete file):

```javascript
/* Offset-tower stability lab — the page twin of `make experiment`.
   Buttons restack 3 line-art blocks at d = 0 / 40 / 90 mm per layer;
   gravity + contacts decide; CoM plumb line flips amber when the
   criterion (CoM outside the support base) is violated. */
(function () {
  'use strict';
  var box = document.getElementById('lab-scene-box');
  var canvas = document.getElementById('lab-scene');
  if (!box || !canvas || !window.Matter) return;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  var M = Matter, W = 560, H = 360;
  var BLUE = '#1d4ed8', INK = '#0f1a2e', GREY = '#8a94a6', AMBER = '#e8a23d';
  var S = 84;                 // block side px  (≙ 200 mm  → 1 mm = 0.42 px)
  var MM = S / 200;           // px per mm
  var GROUND_Y = 331, BASE_X = 292;
  var engine, blocks = [], curD = 40, raf = null, settledAt = 0, started = false;

  function build(dmm) {
    curD = dmm;
    engine = M.Engine.create({ gravity: { x: 0, y: 1, scale: 0.0011 } });
    var ground = M.Bodies.rectangle(W / 2, GROUND_Y + 30, W * 2, 60, { isStatic: true });
    blocks = [0, 1, 2].map(function (i) {
      return M.Bodies.rectangle(
        BASE_X - i * dmm * MM, GROUND_Y - S / 2 - i * S, S, S,
        { friction: 0.6, restitution: 0, density: 0.002 });
    });
    var mouse = M.Mouse.create(canvas);
    function syncMouse() {
      var r = canvas.getBoundingClientRect();
      M.Mouse.setScale(mouse, { x: W / r.width, y: H / r.height });
    }
    syncMouse(); addEventListener('resize', syncMouse);
    var mc = M.MouseConstraint.create(engine, {
      mouse: mouse, constraint: { stiffness: 0.1, damping: 0.1 },
    });
    M.Composite.add(engine.world, blocks.concat([ground, mc]));
    canvas.addEventListener('pointerdown', wake);
  }

  function draw() {
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    ctx.font = '10px ui-monospace, monospace'; ctx.lineJoin = 'round';
    // ground
    ctx.strokeStyle = INK; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(60, GROUND_Y); ctx.lineTo(W - 40, GROUND_Y); ctx.stroke();
    // blocks
    blocks.forEach(function (b, i) {
      ctx.strokeStyle = i === 2 ? BLUE : INK;
      ctx.fillStyle = i === 2 ? 'rgba(29,78,216,.05)' : '#fff';
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      b.vertices.forEach(function (v, j) { j ? ctx.lineTo(v.x, v.y) : ctx.moveTo(v.x, v.y); });
      ctx.closePath(); ctx.fill(); ctx.stroke();
    });
    // CoM plumb + support bracket
    var com = blocks.reduce(function (s, b) { return s + b.position.x; }, 0) / 3;
    var bottom = blocks[0];
    var lo = bottom.position.x - S / 2, hi = bottom.position.x + S / 2;
    var stable = com >= lo && com <= hi;
    var tipped = blocks.some(function (b) {
      return Math.abs(((b.angle % 6.283) + 6.283) % 6.283 - 0) > 0.3 &&
             Math.abs(((b.angle % 6.283) + 6.283) % 6.283 - 6.283) > 0.3;
    });
    var c = stable && !tipped ? BLUE : AMBER;
    ctx.strokeStyle = c; ctx.lineWidth = 1; ctx.setLineDash([4, 6]);
    ctx.beginPath(); ctx.moveTo(com, 36); ctx.lineTo(com, GROUND_Y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = c; ctx.fillText('⌖ CoM', com - 16, 26);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(lo, GROUND_Y + 11); ctx.lineTo(hi, GROUND_Y + 11);
    ctx.moveTo(lo, GROUND_Y + 6); ctx.lineTo(lo, GROUND_Y + 16);
    ctx.moveTo(hi, GROUND_Y + 6); ctx.lineTo(hi, GROUND_Y + 16);
    ctx.stroke();
    ctx.fillStyle = GREY;
    ctx.fillText('support base', (lo + hi) / 2 - 32, GROUND_Y + 28);
    var read = document.getElementById('lab-readout');
    if (read) read.textContent = 'd = ' + curD + ' mm · ' +
      (tipped ? 'TOPPLED — CoM left the base' :
       stable ? 'CoM inside base · STABLE' : 'CoM outside base · UNSTABLE');
  }

  function step(t) {
    M.Engine.update(engine, 1000 / 60);
    draw();
    var maxV = Math.max.apply(null, blocks.map(function (b) { return b.speed; }));
    if (maxV > 0.05) settledAt = t;
    raf = (t - settledAt < 2000) ? requestAnimationFrame(step) : null;
  }
  function wake() { if (!raf) { settledAt = performance.now(); raf = requestAnimationFrame(step); } }
  function restack(d) { build(d); box.classList.add('live'); wake(); }

  document.querySelectorAll('.lab-controls button').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.lab-controls button').forEach(function (x) { x.classList.remove('on'); });
      b.classList.add('on');
      restack(+b.dataset.d);
    });
  });
  document.getElementById('lab-reset').addEventListener('click', function () { restack(curD); });
  new IntersectionObserver(function (es) {
    if (es[0].isIntersecting) { if (!started) { started = true; restack(40); } else wake(); }
    else if (raf) { cancelAnimationFrame(raf); raf = null; }
  }, { threshold: 0.15 }).observe(canvas);
})();
```

- [ ] **Step 2: Verify in browser**

Scroll to SHT 04. Expect: scene initializes on first viewport entry at
d = 40 (stable, blue plumb line). Click `d = 90` → tower restacks and
genuinely topples; plumb line + readout flip amber `TOPPLED`. `d = 0` →
aligned and stable. Blocks draggable; engine sleeps when settled.

- [ ] **Step 3: Commit**

```bash
git add docs/assets/lab.js
git commit -m "feat(site): interactive offset-tower stability scene (page twin of make experiment)"
```

---

### Task 6: Media — experiment figures + social card

**Files:**
- Create: `docs/figures/experiment_aligned.png`, `experiment_offset.png`,
  `experiment_topple.png`, regenerate `docs/figures/social_preview.png`
- Create: `docs/assets/make_social_card.py`

- [ ] **Step 1: Capture experiment frames headless** (uses the live demo)

```bash
rm -f /tmp/demo_live_0*.png /tmp/demo_live_1*.png
SDL_VIDEODRIVER=dummy uv run --extra demo --with "newton[sim] @ ../newton" \
  python -m demo_live --experiment --bench 145 --screenshot-every 5
```

- [ ] **Step 2: Select + downscale the three states**

Pick by inspecting frames (timestamps vary slightly): an aligned-tower
frame from round 1 (~20 s), a 4 cm stepped-tower frame (~50 s), and the
round-3 topple frame (~95 s, status shows `TOPPLED`). Then:

```bash
cp /tmp/demo_live_0200??ms.png docs/figures/experiment_aligned.png   # adjust to chosen frame
cp /tmp/demo_live_0500??ms.png docs/figures/experiment_offset.png
cp /tmp/demo_live_0950??ms.png docs/figures/experiment_topple.png
for f in docs/figures/experiment_*.png; do sips -Z 1280 "$f"; done
ls -la docs/figures/experiment_*.png   # each must be < 350 KB
```

- [ ] **Step 3: Social card generator** — `docs/assets/make_social_card.py`:

```python
"""Renders the OG/Twitter card (1200x630) in the page's blueprint style.
Run:  uv run --extra demo python docs/assets/make_social_card.py"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

W, H, BLUE, INK, GRID = 1200, 630, (29, 78, 216), (15, 26, 46), (29, 78, 216)
pygame.init()
s = pygame.Surface((W, H))
s.fill((255, 255, 255))
for x in range(0, W, 48):
    pygame.draw.line(s, (242, 245, 252), (x, 0), (x, H))
for y in range(0, H, 48):
    pygame.draw.line(s, (242, 245, 252), (0, y), (W, y))
pygame.draw.rect(s, BLUE, (0, 0, W, 6))
# wordmark + title
mono = pygame.font.SysFont("menlo", 26)
big = pygame.font.SysFont("helveticaneue", 88)
sub = pygame.font.SysFont("helveticaneue", 34)
s.blit(mono.render("NEWTON · VLA — LIVE DEMO", True, BLUE), (80, 70))
s.blit(big.render("Real physics. Real language.", True, INK), (76, 150))
s.blit(big.render("One laptop.", True, INK), (76, 250))
s.blit(sub.render("Embodied AI on a MacBook — no GPU, no cloud.", True, (90, 102, 120)), (80, 390))
# cable-robot glyph (right side)
pygame.draw.lines(s, INK, False, [(880, 520), (905, 180), (930, 520)], 3)
pygame.draw.lines(s, INK, False, [(1060, 520), (1085, 180), (1110, 520)], 3)
for a, b in [((905, 185), (960, 350)), ((905, 195), (968, 365)),
             ((1085, 185), (1030, 350)), ((1085, 195), (1022, 365))]:
    pygame.draw.aaline(s, BLUE, a, b)
pts = [(960, 345), (995, 320), (1030, 345), (1030, 385), (995, 408), (960, 385)]
pygame.draw.polygon(s, (240, 244, 253), pts)
pygame.draw.polygon(s, BLUE, pts, 3)
pygame.draw.line(s, INK, (840, 560), (1150, 560), 3)
s.blit(mono.render("REV 0.2.0 · 238 TESTS · 60 FPS CPU-ONLY", True, (138, 148, 166)), (80, 540))
pygame.image.save(s, "docs/figures/social_preview.png")
print("wrote docs/figures/social_preview.png")
```

```bash
uv run --extra demo python docs/assets/make_social_card.py
sips -g pixelWidth docs/figures/social_preview.png   # expect 1200
```

- [ ] **Step 4: Commit**

```bash
git add docs/figures/experiment_*.png docs/figures/social_preview.png docs/assets/make_social_card.py
git commit -m "docs(site): experiment figures + blueprint-style social card"
```

---

### Task 7: Tests green + full verification

- [ ] **Step 1: Run the docs-site test (now expected green)**

Run: `uv run --extra demo python -m unittest demo_live.tests.test_docs_site -v`
Expected: all PASS. If `test_js_bundle_under_100kb_gzip` fails, matter.min.js
alone is ~27 KB gz — investigate hero/lab bloat.

- [ ] **Step 2: Full suite + lint** (docs test joins the suite)

```bash
uv run --extra demo ruff check demo_live/
SDL_VIDEODRIVER=dummy uv run --extra demo --with "newton[sim] @ ../newton" \
  python -m unittest discover -s demo_live/tests 2>&1 | tail -3
```
Expected: `OK`, count ≥ 247 (238 + new docs tests).

- [ ] **Step 3: Browser acceptance pass** (per spec §11)

With `python3 -m http.server 8011 -d docs` running, verify in a browser:
hero drag + tensions + gain meter; tower 0/40 stable, 90 topples, amber
flip; scenes sleep (CPU ~0 when idle); emulate `prefers-reduced-motion:
reduce` in devtools → both canvases hidden, static SVGs shown, no fades;
mobile width 390px → single column, scenes fall back on coarse pointer;
run Lighthouse (devtools) → Perf ≥ 90 mobile, A11y ≥ 95, CLS ≈ 0.

- [ ] **Step 4: Add docs test to CI list** — in
`.github/workflows/tests.yml`, the `coverage run` module list gains one
line `demo_live.tests.test_docs_site \` (it is newton-free), and the
comment count "(91 test methods" becomes the new method count printed by
the suite. Run `make test-ci` to confirm locally.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/tests.yml
git commit -m "ci: run the landing-page parity tests in the no-newton subset"
```

---

### Task 8: Publish

- [ ] **Step 1: Push to Pages** (publishes the 9 pending commits too;
the user's pre-push hook opens a review window — expected):

```bash
git push showcase demo-live-export:main
```

- [ ] **Step 2: Verify live** (Pages legacy build takes ~1-2 min)

```bash
sleep 120 && curl -s https://hollis36.github.io/newton-vla-demo/ | grep -o "REV 0.2.0" | head -1
```
Expected: `REV 0.2.0`. Then a human look at the live URL, including on a phone.
