"""Per-session telemetry logger for the demo.

Writes one CSV row per significant event (mode switch, VLA call, catch
attempt, plan completion, mic recording start/stop, ...) so an instructor
can debrief the session after class:

  - What did students try to say? What did the parser do with it?
  - Which catches succeeded vs missed?
  - Where did the demo fall back to keyword parsing (Claude unavailable)?
  - What was the typical end-to-end command → motion latency?

CSV is intentionally simple: stdlib only, append-as-you-go (so a crash
mid-session still leaves the file readable), and a closing summary line
that's easy to grep.

The logger is *opt-out*: enabled by default with `--telemetry-off` to skip.
A missing `logs/` directory is created automatically; failures to write
are swallowed (telemetry must never crash the demo).
"""

from __future__ import annotations

import contextlib
import csv
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

COLUMNS = (
    "elapsed_s",       # seconds since logger.__init__
    "event",           # short tag, e.g. "vla", "catch", "mode", "voice_fail"
    "user_input",      # raw user text (typed / transcribed); empty for non-input events
    "parsed_action",   # action enum from VLA, e.g. "pick", "stack", "unknown"
    "latency_ms",      # VLA / voice latency where applicable
    "backend",         # "claude", "fallback", "preflight", "voice", ""
    "success",         # "1" / "0" / "" — whether the event "worked"
    "detail",          # free-form extra (color, target, error message, ...)
)


@dataclass
class TelemetryLogger:
    """Writes one CSV row per event. Lifetime = one demo session.

    Use `.event(...)` to append; call `.close()` at exit (or rely on the
    context-manager interface) to flush + print the summary.

    The summary is computed by counting tags in-memory so we don't have to
    re-read the CSV. Cheap (<1 KB per session) but exact.
    """

    path: Path
    start_ts: float = field(default_factory=time.perf_counter)
    # `_file` is the text stream returned by Path.open() — typed as the
    # generic `IO[str]` because the concrete class (TextIOWrapper) is an
    # implementation detail. `_writer` is `csv.writer()` output, which has
    # no stable public type in stdlib; `Any` is the honest annotation.
    _file: IO[str] | None = None
    _writer: Any = None
    _counts: Counter[str] = field(default_factory=Counter)
    _vla_latencies: list[float] = field(default_factory=list)
    _catch_attempts: int = 0
    _catch_successes: int = 0
    _fallbacks: int = 0
    _closed: bool = False

    def __post_init__(self) -> None:
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("w", encoding="utf-8", newline="")
            self._writer = csv.writer(self._file)
            self._writer.writerow(COLUMNS)
            self._file.flush()

    # ----------------------------------------------------------- write API

    def event(
        self,
        tag: str,
        *,
        user_input: str = "",
        parsed_action: str = "",
        latency_ms: float | None = None,
        backend: str = "",
        success: bool | None = None,
        detail: str = "",
    ) -> None:
        """Append one row. All failures are swallowed (telemetry never
        crashes the demo)."""
        if self._closed or self._writer is None:
            return
        with contextlib.suppress(OSError, ValueError):
            self._writer.writerow([
                f"{time.perf_counter() - self.start_ts:.3f}",
                tag,
                _sanitize(user_input),
                parsed_action,
                f"{latency_ms:.1f}" if latency_ms is not None else "",
                backend,
                "" if success is None else ("1" if success else "0"),
                _sanitize(detail),
            ])
            self._file.flush()
        self._counts[tag] += 1
        if tag == "vla" and latency_ms is not None:
            self._vla_latencies.append(latency_ms)
        if backend == "fallback":
            self._fallbacks += 1
        if tag == "catch":
            self._catch_attempts += 1
            if success:
                self._catch_successes += 1

    def close(self) -> tuple[Path, str] | None:
        """Flush, close, and return (path, summary). Idempotent."""
        if self._closed:
            return None
        self._closed = True
        if self._file is not None:
            with contextlib.suppress(OSError):
                self._file.flush()
                self._file.close()
        return self.path, self._summary()

    # ----------------------------------------------------------- summary

    def _summary(self) -> str:
        n_vla = self._counts["vla"]
        avg = (sum(self._vla_latencies) / n_vla) if n_vla and self._vla_latencies else 0.0
        catches = f"{self._catch_successes}/{self._catch_attempts}" if self._catch_attempts else "none"
        return (
            f"VLA: {n_vla} calls (avg {avg:.0f}ms, {self._fallbacks} fallback); "
            f"catches: {catches}; "
            f"mode switches: {self._counts.get('mode', 0)}; "
            f"events: {sum(self._counts.values())}"
        )


# Cell prefixes that trick Excel/Numbers/Sheets into interpreting the cell
# as a formula. We neutralize by prepending a single quote (a long-standing
# spreadsheet convention that forces text mode without showing the quote).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t")


def _sanitize(s: str) -> str:
    """Strip CSV-hostile control chars, neutralize formula-injection
    prefixes, and clamp length so a malformed transcript can't blow up a
    CSV reader (or execute arbitrary spreadsheet formulas when an
    instructor opens the file in Excel)."""
    if not s:
        return ""
    cleaned = s.replace("\r", " ").replace("\n", " ")
    if cleaned[:1] in _FORMULA_PREFIXES:
        cleaned = "'" + cleaned
    return cleaned[:200]


def default_path(prefix: str = "demo", logs_dir: Path | str = "logs") -> Path:
    """Build the default telemetry path: `logs/<prefix>-<YYYYmmdd-HHMMSS>.csv`."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    return Path(logs_dir) / f"{prefix}-{ts}.csv"
