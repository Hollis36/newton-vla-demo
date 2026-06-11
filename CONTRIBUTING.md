# Contributing

Thanks for taking the time to look at this project. It's a single-author
classroom demo, but the contribution surface is the same as any open
source project — bug reports, fixes, and small features are all welcome.

## Local development

This repo expects [`uv`](https://docs.astral.sh/uv/) and Python 3.12+.
The Newton physics engine is an upstream dependency — install it from
<https://github.com/newton-physics/newton> first, then in this repo:

```bash
uv sync --extra demo --extra dev
uv run python -m demo_live --headless-probe   # boot smoke test
```

### Running the demo

```bash
uv run python -m demo_live --fullscreen                # classroom mode
uv run python -m demo_live --fullscreen --industrial   # dual-arm mode
```

See the [README](README.md#what-you-can-say-to-the-arm) for the full
command vocabulary.

### Running the tests

```bash
make test        # needs a sibling Newton clone; see NEWTON= in the Makefile
make test-ci     # the lightweight no-Newton subset that CI runs
```

228 tests pass in ~100 s on Apple Silicon. The full suite needs Newton
(injected from a sibling clone via `uv run --with "newton[sim] @ ../newton"`);
CI runs the 140 tests that don't transitively touch Newton.

If you're adding a new feature, the project follows
[TDD principles](https://en.wikipedia.org/wiki/Test-driven_development) —
write the failing test first, make it pass, then refactor.

### Linting

```bash
uv run ruff check demo_live/
uv run ruff format demo_live/    # auto-format
```

`ruff` config lives in `pyproject.toml` at the repo root.

## Submitting a change

1. **Fork** the repo and create a branch named `<your-handle>/<feature>`
   (matches the upstream Newton convention: `kingcode/...`).
2. **Write tests first** — for a bug, add a regression test that fails
   without your fix.
3. **Run the suite locally** — both tests and `ruff check` must pass.
4. **One logical change per commit** — imperative subject (~50 chars,
   "Fix X" not "Fixed X"), body wrapped at 72 chars explaining the
   _what_ and _why_.
5. **Open a pull request** against `main`. The CI workflow will run
   automatically; fix anything it flags before requesting review.

## Filing an issue

Pick the right template:

- **Bug report** — something doesn't work as documented. Include
  reproduction steps, expected vs. actual behaviour, and the
  `logs/demo-*.csv` from a session that hit it if you can.
- **Feature request** — something missing. Include the audience-facing
  use case ("the arm should …") not the implementation ("we should
  refactor …").

## Code review standards

Even for solo work the project followed a strict review checklist:

- No mutation of shared dicts across threads without a generation
  counter (see `parse_thread` in `__main__.py`).
- No `socket.setdefaulttimeout` or other process-wide side effects.
- No `_keyword_fallback` action enum can leave the parser without
  matching `pipeline.build_plan_from`'s allowlist.
- File-level line counts stay under 800 (current exception:
  `__main__.py` and `scene_legacy.py`, both documented technical debt).
- Every PR keeps `make rehearsal` running end-to-end.

If your change can break any of the above, mention it in the PR.

## License

By contributing, you agree your contributions are licensed under the
MIT License — see [LICENSE](LICENSE).
