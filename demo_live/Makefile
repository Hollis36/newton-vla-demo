# Convenience targets for the demo_live package.
# Run from the newton repo root:   make -C demo_live <target>

.PHONY: help run industrial lint fix test bench probe rehearsal clean

help:
	@echo "Targets:"
	@echo "  run         — launch fullscreen demo"
	@echo "  industrial  — launch dual-arm industrial demo"
	@echo "  lint        — ruff check"
	@echo "  fix         — ruff check --fix + ruff format"
	@echo "  test        — run unittest suite"
	@echo "  bench       — 20 s headless FPS benchmark"
	@echo "  probe       — single-frame headless render to /tmp/demo_live_probe.png"
	@echo "  rehearsal   — 3-min scripted live demo"
	@echo "  clean       — remove __pycache__ and .pyc files"

run:
	cd .. && uv run --extra demo python -m demo_live --fullscreen

industrial:
	cd .. && uv run --extra demo python -m demo_live --fullscreen --industrial

lint:
	cd .. && ruff check demo_live/

fix:
	cd .. && ruff check demo_live/ --fix && ruff format demo_live/

test:
	cd .. && uv run --extra demo python -m unittest discover -s demo_live/tests -v

bench:
	cd .. && SDL_VIDEODRIVER=dummy uv run --extra demo python -m demo_live --bench 20

probe:
	cd .. && SDL_VIDEODRIVER=dummy uv run --extra demo python -m demo_live --headless-probe

rehearsal:
	cd .. && uv run --extra demo python -m demo_live --scripted rehearsal --fullscreen

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
