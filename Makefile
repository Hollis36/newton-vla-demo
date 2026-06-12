# Convenience targets for the newton-vla-demo project.
# Run with `make <target>` from the repo root.
#
# Newton isn't on PyPI yet: the demo and the full test suite expect a
# sibling clone of https://github.com/newton-physics/newton (override
# with `make NEWTON=/path/to/newton <target>`). `uv run --with` injects
# it into the env on the fly — pyproject.toml and uv.lock stay
# newton-free so the lightweight CI subset runs on machines without it.
#
# The package-local Makefile inside demo_live/ has finer-grained
# targets for headless probe / bench / scripted scenarios.

NEWTON ?= ../newton
UV_DEMO = uv run --extra demo --with "newton[sim] @ $(NEWTON)"

.PHONY: help demo industrial real-blocks collab collab-real rehearsal test test-ci lint fix probe bench clean docs newton-check

help:
	@echo "Newton VLA Live Demo — common targets"
	@echo ""
	@echo "  make demo          launch fullscreen classroom mode"
	@echo "  make industrial    launch fullscreen dual-arm industrial mode"
	@echo "  make real-blocks   industrial mode with real rigid-body blocks"
	@echo "  make collab        industrial + two-arm collaborative build (stage-safe)"
	@echo "  make collab-real   collab with real rigid-body blocks (experimental)"
	@echo "  make rehearsal     scripted 3-minute auto rehearsal (industrial)"
	@echo "  make probe         headless one-frame render to /tmp/demo_live_probe.png"
	@echo "  make bench         20-second headless FPS benchmark"
	@echo "  make test          run the full test suite (needs Newton, see NEWTON=)"
	@echo "  make test-ci       run the no-Newton subset that CI runs"
	@echo "  make lint          ruff check demo_live/"
	@echo "  make fix           ruff format + autofix"
	@echo "  make docs          xelatex compile report + slides"
	@echo "  make clean         remove __pycache__ + LaTeX build artefacts"

newton-check:
	@test -f "$(NEWTON)/pyproject.toml" || { \
	  echo "error: Newton clone not found at '$(NEWTON)'."; \
	  echo "  git clone https://github.com/newton-physics/newton ../newton"; \
	  echo "  (or pass NEWTON=/path/to/newton)"; \
	  exit 1; }

demo: newton-check
	$(UV_DEMO) python -m demo_live --fullscreen

industrial: newton-check
	$(UV_DEMO) python -m demo_live --fullscreen --industrial

real-blocks: newton-check
	$(UV_DEMO) python -m demo_live --fullscreen --industrial --real-blocks

# Stage-safe flagship: teleport blocks place exactly where the relay puts
# them, cycle after cycle. Adding --real-blocks is physically honest but
# blocks bounce/topple into each other across build/teardown cycles —
# keep that combination for the "physics is real" beat, not the show loop.
collab: newton-check
	$(UV_DEMO) python -m demo_live --fullscreen --industrial --collab

collab-real: newton-check
	$(UV_DEMO) python -m demo_live --fullscreen --industrial --real-blocks --collab

rehearsal: newton-check
	$(UV_DEMO) python -m demo_live --fullscreen --industrial --scripted rehearsal

probe: newton-check
	SDL_VIDEODRIVER=dummy $(UV_DEMO) python -m demo_live --headless-probe

bench: newton-check
	SDL_VIDEODRIVER=dummy $(UV_DEMO) python -m demo_live --bench 20

test: newton-check
	$(UV_DEMO) python -m unittest discover -s demo_live/tests -v

test-ci:
	SDL_VIDEODRIVER=dummy uv run --extra demo python -m unittest -v \
	  demo_live.tests.test_voice_fuzzy \
	  demo_live.tests.test_telemetry \
	  demo_live.tests.test_vla_parser \
	  demo_live.tests.test_vla_subprocess \
	  demo_live.tests.test_effects

lint:
	uv run ruff check demo_live/

fix:
	uv run ruff check demo_live/ --fix
	uv run ruff format demo_live/

docs:
	cd docs && xelatex -interaction=nonstopmode report.tex && xelatex -interaction=nonstopmode report.tex
	cd docs && xelatex -interaction=nonstopmode slides.tex && xelatex -interaction=nonstopmode slides.tex

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -f docs/*.aux docs/*.log docs/*.out docs/*.toc docs/*.nav docs/*.snm docs/*.vrb
