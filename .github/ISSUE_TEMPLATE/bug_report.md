---
name: Bug report
about: Something doesn't work as documented in README / REHEARSAL.
title: '[bug] '
labels: bug
---

## Reproduction

<!-- The smallest sequence of keys / commands that triggers the bug. -->

1.
2.
3.

## Expected behaviour

<!-- Per README / REHEARSAL.md or your own reasonable expectation. -->

## Actual behaviour

<!-- What happened instead. Paste the on-screen status log or
     stderr output if relevant. -->

## Environment

- OS: <!-- macOS 14.x / Linux distro / etc. -->
- Python: `python --version`
- Newton commit: <!-- output of `cd path/to/newton && git rev-parse HEAD` -->
- pygame-ce version: `python -c "import pygame; print(pygame.version.ver)"`
- Render mode: <!-- `--industrial` or default classroom -->
- Mode when bug fired: <!-- IDLE / BALL CATCH / TALK TO ARM / TRANSCRIBING -->

## Telemetry CSV

<!-- If the bug happened during an interactive session, paste the
     last 20 rows of logs/demo-<ts>.csv. They contain exact
     timestamps and event sequences that make repro much easier. -->

```
elapsed_s,event,user_input,parsed_action,latency_ms,backend,success,detail
```

## Anything else?
