"""Cascade backend: fast model first, accurate model only when needed.

Typical use: run TAMEV (22.8M, ~7 ms on CPU) first. If its confidence is at
or above ``threshold``, use its answer. Otherwise, escalate to a heavier
model (OpenJev 1.7B, ~200-2000 ms) for a second opinion.

For routing / triage workloads, TAMEV alone is often sufficient for the
"easy" 70-90% of cases, which turns a 1-9 s per-request latency into
sub-100 ms for the majority of requests.
"""

from __future__ import annotations

from typing import Any, ClassVar

from open_decide.backends.base import DecisionBackend
from open_decide.models import Decision, QuestionType


class CascadeBackend(DecisionBackend):
    """Two-stage backend: fast, then accurate on low confidence."""

    name: ClassVar[str] = "cascade"

    def __init__(
        self,
        fast: str = "tamev",
        accurate: str = "openjev",
        threshold: float = 0.75,
        fast_kwargs: dict[str, Any] | None = None,
        accurate_kwargs: dict[str, Any] | None = None,
    ) -> None:
        # Local import to avoid a circular dependency at module load.
        from open_decide.backends import get_backend

        self._fast = get_backend(fast, **(fast_kwargs or {}))
        self._accurate = get_backend(accurate, **(accurate_kwargs or {}))
        self._threshold = threshold
        self._fast_name = fast
        self._accurate_name = accurate

    async def decide(
        self,
        context: str,
        question: str,
        options: list[str],
        question_type: QuestionType,
    ) -> Decision:
        fast = await self._fast.decide(context, question, options, question_type)

        if fast.confidence >= self._threshold:
            return fast

        accurate = await self._accurate.decide(context, question, options, question_type)
        # Annotate the decision so callers (and traces) can see the escalation.
        return accurate.model_copy(
            update={
                "escalated": True,
                "fast_confidence": fast.confidence,
            }
        )

    def unload(self) -> None:
        for backend in (self._fast, self._accurate):
            unload = getattr(backend, "unload", None)
            if callable(unload):
                unload()
