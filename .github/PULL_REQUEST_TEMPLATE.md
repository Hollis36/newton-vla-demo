<!--
Thanks for sending a PR. Please give the title an imperative subject
under ~50 chars ("Fix X", not "Fixed X") and use this body to explain
the *what* and the *why*.
-->

## Summary

<!-- One or two sentences on what this changes. -->

## Why

<!-- The problem this solves. If it's a bug, link the issue.
     If it's a feature, the audience-facing use case. -->

## How it works

<!-- The shape of the change. Where the new code lives, what the
     control flow looks like, any subtle invariants the reader
     needs to keep in mind. -->

## Testing

<!-- Tick everything that applies. -->

- [ ] Added / updated unit tests under `demo_live/tests/`.
- [ ] `uv run python -m unittest discover -s demo_live/tests` passes locally (214 / 214).
- [ ] `ruff check demo_live/` clean.
- [ ] `make -C demo_live rehearsal` runs end-to-end without crashing.
- [ ] If user-facing: README / REHEARSAL.md updated.

## Risk

<!-- Anything that could break in production:
     - State that crosses thread boundaries
     - Newton API assumptions
     - Frame-rate / latency sensitive paths
     - Render path differences between scene/ and scene_legacy.py
-->
