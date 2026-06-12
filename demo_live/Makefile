# Convenience targets for the demo_live package.
# Run from the repo root:   make -C demo_live <target>
#
# Newton is injected from a sibling clone (../newton relative to the
# repo root); override with `make NEWTON=/path/to/newton <target>`.

NEWTON ?= ../newton
UV_DEMO = uv run --extra demo --with "newton[sim] @ $(NEWTON)"

.PHONY: help run industrial real-blocks collab lint fix test bench probe rehearsal clean

help:
	@echo "Targets:"
	@echo "  run         — launch fullscreen demo"
	@echo "  industrial  — launch dual-arm industrial demo"
	@echo "  real-blocks — industrial demo with real rigid-body blocks"
	@echo "  collab      — industrial + two-arm collaborative build (stage-safe)"
	@echo "  lint        — ruff check"
	@echo "  fix         — ruff check --fix + ruff format"
	@echo "  test        — run unittest suite (needs Newton, see NEWTON=)"
	@echo "  bench       — 20 s headless FPS benchmark"
	@echo "  probe       — single-frame headless render to /tmp/demo_live_probe.png"
	@echo "  rehearsal   — 3-min scripted live demo"
	@echo "  clean       — remove __pycache__ and .pyc files"

run:
	cd .. && $(UV_DEMO) python -m demo_live --fullscreen

industrial:
	cd .. && $(UV_DEMO) python -m demo_live --fullscreen --industrial

real-blocks:
	cd .. && $(UV_DEMO) python -m demo_live --fullscreen --industrial --real-blocks

collab:
	cd .. && $(UV_DEMO) python -m demo_live --fullscreen --industrial --collab

lint:
	cd .. && ruff check demo_live/

fix:
	cd .. && ruff check demo_live/ --fix && ruff format demo_live/

test:
	cd .. && $(UV_DEMO) python -m unittest discover -s demo_live/tests -v

bench:
	cd .. && SDL_VIDEODRIVER=dummy $(UV_DEMO) python -m demo_live --bench 20

probe:
	cd .. && SDL_VIDEODRIVER=dummy $(UV_DEMO) python -m demo_live --headless-probe

rehearsal:
	cd .. && $(UV_DEMO) python -m demo_live --scripted rehearsal --fullscreen

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
