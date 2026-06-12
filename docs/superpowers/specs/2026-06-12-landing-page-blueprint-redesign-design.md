# Landing Page Redesign — "Blueprint Minimal" Design Spec

Date: 2026-06-12
Status: awaiting user review
Target: `docs/index.html` (GitHub Pages, served from `showcase/main` `/docs`)

## 1. Goal & positioning

Replace the current "generic SaaS landing" page with a **blue-white,
engineering-drawing minimal** page that reads as a precision-instrument
artifact. The page is a **personal portfolio piece** (admissions
committees, supervisors, recruiters). The lab identity (electromechanical
integrated manufacturing / cable-driven parallel robots / electromechanical
coupling) appears as **aesthetic and conceptual DNA only — no lab name or
affiliation text anywhere** (can be added later).

Non-goals: dark mode, CMS, multi-page, i18n switcher, analytics.

## 2. Narrative structure (drawing-sheet chapters)

Every section carries a sheet number (`SHT 0n/05`) in the chapter label.

```
HEADER    hairline top rule in blue · "NEWTON · VLA" wordmark ·
          mono meta: DOC NO. NVD-2026 / REV 0.2.0 / SHT 01-05
SHT 01    HERO — headline + tagline + 2 CTAs (Demo film ▶, GitHub ↗)
          right: INTERACTIVE CABLE-ROBOT SCENE (see §4)
SPEC ROW  4 key figures, thin blue left-rules:
          238 tests · 60 fps CPU-only · 0.3 ms physics step (39×↓) ·
          1 ms command→motion
SHT 02    CONTROL LOOP — hybrid VLA pipeline drawn as a control block
          diagram: input → keyword feedforward (1 ms, solid) → 3-DOF arm
          (min-jerk + PD) with Claude as slow feedback branch
          (9.4 s, dashed). SVG strokes draw in on scroll.
SHT 03    THREE MODES — ball-catch (MPC) / talk-to-arm (VLA) / stability
          lecture. Screenshots + the rehearsal MP4 framed as instrument
          viewports: 1px ink border + mono figure captions
          ("FIG. 3-1 — Ball catch, MPC intercept").
SHT 04    STABILITY LAB — the offset-tower experiment, INTERACTIVE
          (see §5): line-art blocks, CoM plumb line, d = 0/40/90 mm,
          theory annotation d > h/1.5 ≈ 67 mm.
SHT 05    ARCHITECTURE — module table + performance table in mono
          "BOM / spec-sheet" styling. Links: design report PDF,
          slides PDF, REHEARSAL.md.
FOOTER    drawing title block: DRAWN Hollis36 / REV / DATE / links.
          No affiliation text.
```

## 3. Visual system

- Background pure white `#ffffff`; hairline blue grid
  (`rgba(29,78,216,.05)`, 48px) **only inside the hero**; all other
  sections plain white with generous whitespace.
- One blue `#1d4ed8` (primary, links, accents) + ink `#0f1a2e` +
  greys `#5a6678 / #8a94a6 / #e3e8f0`. Amber `#e8a23d` reserved for
  exactly two semantic uses: tower-topple states and cabin deviation Δ.
- No shadows, no gradients, no glow. Radii 2–3px uniformly.
- Type: headings **Inter** (or Instrument Sans), 400/500 weight, large
  sizes with tight leading (luxury via scale contrast 38–72px vs 12px,
  not weight); data/labels **IBM Plex Mono**. System CJK fallback.
- Rules: 1px `#e3e8f0` section rules; 1.5px ink rule above footer;
  1px blue rule under header.

## 4. Hero scene — six-cable parallel robot (lab DNA)

Line-art interactive miniature of a cable-driven parallel feed-support
robot (recognizably FAST-like to insiders; never named).

- **Physics (matter.js)**: 2 side towers + 1 center tower (static),
  hexagonal cabin body (~30 t scaled) suspended by 6 distance
  constraints (3 visible pairs), gravity on; drag the cabin → cables
  re-tension; release → damped swing back to the work point.
- **Live annotations (mono, 9px)**: per-pair cable tension `T₁/T₂ … N`
  (stroke width maps to tension); target point ⌖; deviation `Δ mm` in
  amber when cabin is off-target.
- **Electromechanical-coupling meter**: small "GAIN" bar
  (机电耦合 · structure → EM performance): bar and `−x.x dB` follow
  cabin deviation. One-line caption under the scene explains it.
- **Secondary elements**: parabolic reflector arc below (2 strokes),
  Stewart-platform hint under the cabin (3 short struts), all
  non-physical decoration.
- **Rendering**: canvas, white bg, 1.2px ink outlines, blue cables;
  no textures. Engine sleeps when settled & off-viewport
  (IntersectionObserver). Static SVG fallback for
  `prefers-reduced-motion` and `pointer: coarse` + narrow screens.

## 5. SHT 04 scene — offset-tower stability experiment (project)

Same engine instance re-used (one matter.js runtime, two worlds —
lazy-init each on first viewport entry).

- 3 line-art blocks; buttons `d = 0 / 40 / 90 mm` restack the tower at
  that per-layer offset; user can also nudge blocks by drag.
- CoM plumb line (dashed blue) + support-base bracket on the ground;
  line turns amber + `UNSTABLE` label when CoM exits the base;
  90 mm genuinely topples under gravity.
- `reset ⟳` mono button bottom-right; theory annotation
  `topple when d > h/1.5 ≈ 67 mm` always visible.
- Mirrors the real `--experiment` mode of the demo (schedule 0/4/9 cm)
  so the web toy and the Python demo tell the same physics story.

## 6. Motion budget (restraint)

Exactly three behaviors, nothing else:
1. Section fade-up on first scroll into view (CSS, 12px translate,
   240 ms, once).
2. SHT 02 diagram strokes draw in on scroll (SVG stroke-dashoffset,
   IntersectionObserver-triggered, once).
3. Spec-row numbers count up once when first visible.
All gated behind `prefers-reduced-motion: no-preference`.

## 7. Media plan

- Re-capture stability-experiment frames (3 states + topple) headless
  at 1920×1080, downscale to ≤1280w, strip to ≤300 KB each.
- Existing rehearsal MP4 + catch/stack screenshots reframed with ink
  borders + FIG captions; reuse current files where adequate.
- New OG image: blueprint-style social card (white, blue wordmark,
  cable-robot line art) — static export of the hero scene.

## 8. Engineering

- Single `docs/index.html` + `docs/assets/{hero.js, lab.js,
  matter.min.js}`; matter.js vendored locally (~80 KB min, ~25 KB gz);
  total JS budget < 100 KB gzip; no build step, no framework.
- Update all stats from the repo's current truth (238 tests, 7730
  lines, v0.2.0, perf table numbers) — the page must not drift from
  README claims.
- Accessibility: AA contrast, alt text on all figures, keyboard-visible
  focus, scenes are progressive enhancement over static content.
- SEO/OG: keep existing meta, update description + new social card.

## 9. Deployment

Pages serves `main:/docs` (legacy build). Work lands on
`demo-live-export` (currently ahead 7 commits), then push to
`showcase/main` — the push publishes both the new page and the pending
feature commits. User's git hooks open a review before push.

## 10. Risks & mitigations

- **Cable physics feels mushy** → tune constraint stiffness/damping
  first; fallback: stiff rods (2 constraints per pair) with drawn-only
  middle cables.
- **Two physics scenes on one page jank on low-end** → one engine,
  lazy init, sleep when settled, cap at 60 Hz fixed timestep,
  pause off-viewport.
- **Line-art reads "unfinished" to laypeople** → captions under each
  scene state what is being simulated; FIG numbering signals intent.
- **Mobile** → scenes degrade to static SVG; layout single-column;
  spec row wraps 2×2.

## 11. Acceptance checklist

- [ ] Hero cabin draggable, tension labels update, gain meter follows Δ
- [ ] SHT 04 tower: 0/40 stable, 90 topples; plumb line flips amber
- [ ] All numeric claims match repo (badge parity with README)
- [ ] Lighthouse: Perf ≥ 90 mobile, A11y ≥ 95, no CLS from scenes
- [ ] `prefers-reduced-motion` shows fully static page
- [ ] No lab name/affiliation text anywhere
- [ ] Pushed to showcase/main, live at hollis36.github.io/newton-vla-demo
