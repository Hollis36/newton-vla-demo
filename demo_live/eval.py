"""Reproducible evaluation harness for the VLA intent parser.

Runs the parser over a curated, bilingual golden set and reports per-case
pass/fail plus overall accuracy. This turns the "the keyword fallback
handles every rehearsed command" claim into something you can *verify* on
every commit, and gives a single command to benchmark any backend:

    python -m demo_live.eval                      # keyword parser (offline)
    python -m demo_live.eval --backend cli        # through `claude --print`
    python -m demo_live.eval --backend api        # through the Anthropic SDK
    python -m demo_live.eval --json               # machine-readable output

Exit code is non-zero when accuracy drops below `--min-accuracy` (default
1.0 for the keyword backend), so it doubles as a CI regression gate.

The golden set is deliberately scoped to commands the deterministic parser
must always get right — adding a case that the keyword backend fails turns
the CI gate red, which is exactly the signal we want.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field

from .vla import VLAResult, parse_command


@dataclass(frozen=True)
class GoldCase:
    """One golden example. Only the non-None expectations are checked, so a
    case can assert just the action, or also the colour / colours / the sign
    of the drive/place target."""

    utterance: str
    action: str
    color: str | None = None
    colors: tuple[str, ...] | None = None
    target_sign: int | None = None  # sign of target[0]: -1, 0, +1, or None
    note: str = ""


# Bilingual golden set — every action, English + 中文. Curated so the
# deterministic keyword parser scores 100%; the LLM backends should match.
GOLD: tuple[GoldCase, ...] = (
    # --- pick -----------------------------------------------------------
    GoldCase("pick up the red block", "pick", color="red"),
    GoldCase("grab the green cube", "pick", color="green"),
    GoldCase("take the yellow one", "pick", color="yellow"),
    GoldCase("拿起蓝色方块", "pick", color="blue", note="zh: pick blue"),
    GoldCase("抓住红色的方块", "pick", color="red", note="zh: grab red"),
    # --- stack ----------------------------------------------------------
    GoldCase("build a tower", "stack", colors=("red", "green", "blue")),
    GoldCase("stack red green and blue", "stack", colors=("red", "green", "blue")),
    GoldCase("stack red and blue", "stack", colors=("red", "blue")),
    GoldCase("搭一个塔", "stack", note="zh: default tower"),
    GoldCase("叠红色和绿色", "stack", colors=("red", "green"), note="zh: stack red+green"),
    # --- place ----------------------------------------------------------
    GoldCase("put it on the left", "place", target_sign=-1),
    GoldCase("put it on the right", "place", target_sign=1),
    GoldCase("place the yellow block on the left", "place", color="yellow", target_sign=-1),
    GoldCase("把蓝色方块放到左边", "place", color="blue", target_sign=-1, note="zh: place blue left"),
    # --- drive ----------------------------------------------------------
    GoldCase("drive left", "drive", target_sign=-1),
    GoldCase("drive right", "drive", target_sign=1),
    GoldCase("go to the blue block", "drive", target_sign=1),
    GoldCase("drive to the red block", "drive", target_sign=1),
    GoldCase("往右走", "drive", target_sign=1, note="zh: drive right"),
    GoldCase("往左移动", "drive", target_sign=-1, note="zh: drive left"),
    # --- home -----------------------------------------------------------
    GoldCase("go home", "home"),
    GoldCase("reset", "home"),
    GoldCase("回位", "home", note="zh: home"),
    GoldCase("归零", "home", note="zh: reset"),
    # --- gestures -------------------------------------------------------
    GoldCase("wave at the crowd", "wave"),
    GoldCase("say hi", "wave"),
    GoldCase("挥手", "wave", note="zh: wave"),
    GoldCase("point at the audience", "point", colors=("audience",)),
    GoldCase("point right", "point", colors=("right",)),
    GoldCase("point at something", "point", colors=("left",)),
    GoldCase("take a bow", "bow"),
    GoldCase("鞠躬", "bow", note="zh: bow"),
    GoldCase("dance for us", "dance"),
    GoldCase("跳舞", "dance", note="zh: dance"),
    # --- unknown --------------------------------------------------------
    GoldCase("sdfjklsdfjkl", "unknown"),
)


@dataclass
class CaseResult:
    case: GoldCase
    result: VLAResult
    ok: bool
    detail: str


@dataclass
class EvalReport:
    backend: str
    results: list[CaseResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.ok]


def check_case(case: GoldCase, result: VLAResult) -> tuple[bool, str]:
    """Compare a parse against a golden case. Only non-None expectations are
    enforced. Returns (ok, human-readable detail)."""
    if result.action != case.action:
        return False, f"action {result.action!r} != {case.action!r}"
    if case.color is not None and result.color != case.color:
        return False, f"color {result.color!r} != {case.color!r}"
    if case.colors is not None and tuple(result.colors or ()) != case.colors:
        return False, f"colors {tuple(result.colors or ())} != {case.colors}"
    if case.target_sign is not None:
        if result.target is None:
            return False, "target is None (expected a target)"
        got = result.target[0]
        sign = (got > 0) - (got < 0)
        if sign != case.target_sign:
            return False, f"target sign {sign:+d} != {case.target_sign:+d} (x={got:+.2f})"
    return True, "ok"


def evaluate(
    backend: str = "keyword",
    *,
    timeout: float = 8.0,
    model: str | None = None,
    cases: tuple[GoldCase, ...] = GOLD,
) -> EvalReport:
    """Run `cases` through `parse_command` on the given backend and collect
    per-case results."""
    report = EvalReport(backend=backend)
    for case in cases:
        result = parse_command(case.utterance, timeout=timeout, backend=backend, model=model)
        ok, detail = check_case(case, result)
        report.results.append(CaseResult(case, result, ok, detail))
    return report


def format_report(report: EvalReport) -> str:
    """Render a human-readable table + summary line."""
    lines = [f"VLA eval — backend={report.backend}  cases={report.total}", ""]
    for r in report.results:
        mark = "PASS" if r.ok else "FAIL"
        utt = r.case.utterance if len(r.case.utterance) <= 32 else r.case.utterance[:29] + "..."
        lines.append(f"  [{mark}] {utt:<34} → {r.result.action:<7} {'' if r.ok else '(' + r.detail + ')'}")
    pct = report.accuracy * 100
    lines.append("")
    lines.append(f"accuracy: {report.passed}/{report.total} = {pct:.1f}%")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the VLA intent parser on the golden set.")
    parser.add_argument("--backend", default="keyword",
                        choices=["keyword", "cli", "api", "learned"],
                        help="language backend to evaluate (default: keyword)")
    parser.add_argument("--model", default=None, help="model alias/id for cli/api backends")
    parser.add_argument("--timeout", type=float, default=8.0, help="per-command timeout (s)")
    parser.add_argument("--min-accuracy", type=float, default=None,
                        help="fail (exit 1) below this accuracy; default 1.0 for keyword, 0.0 otherwise")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    report = evaluate(args.backend, timeout=args.timeout, model=args.model)
    min_acc = args.min_accuracy
    if min_acc is None:
        min_acc = 1.0 if args.backend == "keyword" else 0.0

    if args.json:
        payload = {
            "backend": report.backend,
            "total": report.total,
            "passed": report.passed,
            "accuracy": report.accuracy,
            "failures": [
                {"utterance": r.case.utterance, "expected": r.case.action,
                 "got": r.result.action, "detail": r.detail}
                for r in report.failures
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))

    return 0 if report.accuracy >= min_acc else 1


if __name__ == "__main__":
    raise SystemExit(main())
