"""Learned intent-policy seam (experimental).

The Claude backends in `vla.py` parse a command with a foundation model.
This module adds a pluggable seam for a *learned* policy — a model trained
to map an utterance onto one of the demo's discrete actions — so the demo
can showcase a real learned-model path alongside the LLM and keyword paths,
**no GPU and no cloud required**.

A "policy" only has to satisfy `LearnedPolicy`: a `name` and a `parse()`
that returns the same action dict the rest of the pipeline already speaks
(see `vla.py` for the schema). Three things ship here:

  * `MockLearnedPolicy`  — deterministic reference. Wraps the keyword parser
    and tags the source, so the seam is fully exercised in tests without any
    heavyweight dependency. This is the default for the "learned" backend.
  * `TransformersZeroShotPolicy` — a real CPU-runnable adapter. Uses a
    HuggingFace zero-shot text-classification pipeline (e.g. a distilled
    NLI model, a few hundred MB) to score the utterance against the action
    labels. Lazy-imports `transformers`; raises `PolicyUnavailable` with
    install hints if the dependency or model is missing.
  * The `LearnedPolicy` protocol + `get_default_policy()` / `set_default_policy()`.

Wire a policy into the demo with `vla.set_learned_policy(...)` and run with
`--vla-backend learned` (or `NEWTON_VLA_BACKEND=learned`).

Bring-your-own checkpoint. To plug a genuine sensorimotor VLA such as
**SmolVLA** (lerobot), implement the same `parse()` contract in an adapter
that loads the checkpoint and maps its output onto the action schema — the
backend wiring does not change. `TransformersZeroShotPolicy` is the worked
example of how an external model slots into the seam.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# The label set the learned path predicts over. A subset of vla.KNOWN_ACTIONS
# (we drop "unknown", which is the implicit low-confidence outcome).
ACTION_LABELS = (
    "pick", "place", "stack", "drive", "home", "wave", "point", "bow", "dance",
)


class PolicyUnavailable(RuntimeError):
    """Raised when a learned policy's dependencies or checkpoint are missing.

    Carries an actionable install/usage hint in its message."""


@runtime_checkable
class LearnedPolicy(Protocol):
    """The contract a learned intent policy must satisfy to back the
    "learned" VLA backend."""

    name: str

    def parse(
        self,
        user_input: str,
        world_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Return an action dict (vla.py schema) for `user_input`, or None
        to defer to the keyword fallback."""
        ...


class MockLearnedPolicy:
    """Deterministic reference policy.

    Reuses the keyword parser for its decision so the integration seam is
    fully testable with zero extra dependencies, and re-tags the reason so a
    viewer can see the learned path actually fired."""

    name = "mock-learned"

    def parse(
        self,
        user_input: str,
        world_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        # Imported here to avoid a circular import at module load time
        # (vla.py imports this module lazily from the "learned" backend).
        from .vla import _keyword_fallback

        data = dict(_keyword_fallback(user_input))
        data["reason"] = f"[{self.name}] {data.get('reason', '')}".strip()
        return data


class TransformersZeroShotPolicy:
    """Learned intent policy backed by a HuggingFace zero-shot classifier.

    Scores the utterance against `ACTION_LABELS` with an NLI model that runs
    happily on a MacBook CPU. The model and `transformers` are loaded lazily
    on first use; if either is unavailable a `PolicyUnavailable` is raised
    with an install hint. Colour / target extraction is delegated to the
    keyword parser — the learned model decides the *action*, the deterministic
    rules fill in the arguments. This keeps the adapter honest: a real learned
    model picks the verb, exactly where intent classification adds value.

    This class is intentionally not exercised in CI (it would pull in torch);
    it documents and implements the external-model integration point.
    """

    name = "transformers-zero-shot"

    def __init__(
        self,
        model: str = "valhalla/distilbart-mnli-12-1",
        *,
        min_score: float = 0.30,
    ) -> None:
        self.model = model
        self.min_score = min_score
        self._pipeline: Any = None

    def _ensure_loaded(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from transformers import pipeline
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise PolicyUnavailable(
                "TransformersZeroShotPolicy needs the `learned` extra: "
                "`uv sync --extra learned` (installs transformers + torch). "
                "Or use the default mock policy / a Claude backend."
            ) from exc
        try:
            self._pipeline = pipeline("zero-shot-classification", model=self.model)
        except Exception as exc:  # pragma: no cover - network / checkpoint missing
            raise PolicyUnavailable(
                f"Could not load zero-shot model {self.model!r}: {exc}. "
                "Pre-download it or pass a local checkpoint path."
            ) from exc

    def parse(
        self,
        user_input: str,
        world_state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        from .vla import _keyword_fallback

        self._ensure_loaded()
        result = self._pipeline(user_input, list(ACTION_LABELS))
        top_label = result["labels"][0]
        top_score = float(result["scores"][0])
        if top_score < self.min_score:
            return None  # low confidence → defer to keyword fallback

        # Let the deterministic rules fill in colour / colours / target; the
        # learned model only overrides which verb we committed to.
        data = dict(_keyword_fallback(user_input))
        data["action"] = top_label
        data["reason"] = f"[{self.name}] {top_label} (p={top_score:.2f})"
        return data


# ----------------------------------------------------------------- registry
_default_policy: LearnedPolicy | None = None


def get_default_policy() -> LearnedPolicy:
    """Return the process-wide default learned policy (a `MockLearnedPolicy`
    until `set_default_policy` installs something else)."""
    global _default_policy
    if _default_policy is None:
        _default_policy = MockLearnedPolicy()
    return _default_policy


def set_default_policy(policy: LearnedPolicy) -> None:
    """Install the process-wide default learned policy."""
    global _default_policy
    _default_policy = policy
