# Convenience targets for the newton-vla-demo project.
# Run with `make <target>` from the repo root.
#
# The package-local Makefile inside demo_live/ has finer-grained
# targets for headless probe / bench / scripted scenarios.

.PHONY: help demo industrial rehearsal test lint fix probe bench clean docs

help:
	@echo "Newton VLA Live Demo — common targets"
	@echo ""
	@echo "  make demo          launch fullscreen classroom mode"
	@echo "  make industrial    launch fullscreen dual-arm industrial mode"
	@echo "  make rehearsal     scripted 3-minute auto rehearsal (industrial)"
	@echo "  make probe         headless one-frame render to /tmp/demo_live_probe.png"
	@echo "  make bench         20-second headless FPS benchmark"
	@echo "  make test          run the full 214-test suite"
	@echo "  make lint          ruff check demo_live/"
	@echo "  make fix           ruff format + autofix"
	@echo "  make docs          xelatex compile report + slides"
	@echo "  make clean         remove __pycache__ + LaTeX build artefacts"

demo:
	uv run python -m demo_live --fullscreen

industrial:
	uv run python -m demo_live --fullscreen --industrial

rehearsal:
	uv run python -m demo_live --fullscreen --industrial --scripted rehearsal

probe:
	SDL_VIDEODRIVER=dummy uv run python -m demo_live --headless-probe

bench:
	SDL_VIDEODRIVER=dummy uv run python -m demo_live --bench 20

test:
	uv run python -m unittest discover -s demo_live/tests -v

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
