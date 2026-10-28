"""A deterministic mock backend used for tests and demos.

It does not require any model download. Given the same inputs it always
returns the same decision, which makes it suitable for unit tests, examples
and for wiring the engine before plugging a real decision model.
"""

from __future__ import annotations

import hashlib
import time
from typing import ClassVar

from open_decide.backends.base import DecisionBackend
from open_decide.models import Decision, QuestionType


class MockBackend(DecisionBackend):
    """Deterministic, hash-based backend.

    Behaviour:

    1. If ``keywords`` is provided and a keyword is found (case-insensitive)
       in the context AND its mapped label is one of the allowed options,
       the decision is forced to that label with a high confidence.
    2. Otherwise each option is scored by a stable hash of
       ``(context, question, option)`` and the scores are normalised to sum
       to 1. The highest-scoring option wins.

    The keyword map is meant to make demos sensible (e.g. map ``"urgent"``
    to the label ``"yes"`` for an urgency question) without adding magic to
    the engine.
    """

    name: ClassVar[str] = "mock"

    def __init__(self, keywords: dict[str, str] | None = None) -> None:
        self._keywords = keywords or {}

    async def decide(
        self,
        context: str,
        question: str,
        options: list[str],
        question_type: QuestionType,
    ) -> Decision:
        start = time.perf_counter()

        label = self._keyword_match(context, options)
        if label is not None:
            scores = self._uniform_scores(options, forced=label, forced_score=0.99)
            return Decision(
                label=label,
                confidence=0.99,
                scores=scores,
                latency_ms=(time.perf_counter() - start) * 1000.0,
            )

        raw: list[float] = []
        for opt in options:
            digest = hashlib.sha256(f"{context}|{question}|{opt}".encode()).digest()
            raw.append(int.from_bytes(digest[:8], "big") / 2**64)

        total = sum(raw) or 1.0
        scores = {opt: value / total for opt, value in zip(options, raw, strict=True)}
        label = max(scores, key=lambda k: scores[k])

        return Decision(
            label=label,
            confidence=scores[label],
            scores=scores,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )

    def _keyword_match(self, context: str, options: list[str]) -> str | None:
        lowered = context.lower()
        for keyword, target in self._keywords.items():
            if keyword.lower() in lowered and target in options:
                return target
        return None

    @staticmethod
    def _uniform_scores(
        options: list[str],
        forced: str,
        forced_score: float,
    ) -> dict[str, float]:
        if len(options) == 1:
            return {options[0]: 1.0}
        rest = (1.0 - forced_score) / (len(options) - 1)
        return {opt: (forced_score if opt == forced else rest) for opt in options}
