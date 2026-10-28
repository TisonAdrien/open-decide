"""OpenJev backend: local, open reproduction of a Jev-class decision engine.

Wraps ``openjev-ai`` (which installs ``wev-ai``, imported as ``wev``) and runs
a typed decision model locally. The model is loaded lazily on first ``decide``.

OpenJev exposes the same typed primitives as Jev: ``noul``, ``choice``,
``score``, answered in one forward pass with calibrated confidence.

Reference:
    https://pypi.org/project/openjev-ai/
    https://github.com/alanhuangyoo/OpenJev
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, ClassVar

from open_decide.backends.base import BackendNotAvailable, DecisionBackend
from open_decide.context import DEFAULT_MAX_CHARS, truncate_context
from open_decide.models import Decision, QuestionType

_DEFAULT_MODEL_ID = "alanhuangya/OpenJev-1.7B"


class OpenJevBackend(DecisionBackend):
    """Decision backend backed by an OpenJev model.

    Args:
        model_id: Hugging Face model id of an OpenJev checkpoint.
            Defaults to the smallest tier (1.7B) for CPU-friendly runs.
        device: Torch device string (``"cpu"``, ``"cuda"``, ``"mps"``).
    """

    name: ClassVar[str] = "openjev"

    def __init__(
        self,
        model_id: str = _DEFAULT_MODEL_ID,
        *,
        device: str = "cpu",
        max_context_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._max_context_chars = max_context_chars
        self._model: Any | None = None
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> Any:
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model

            try:
                import wev
            except ImportError as exc:
                raise BackendNotAvailable(
                    "OpenJevBackend requires the 'openjev' extra. "
                    "Install it with: uv sync --extra openjev "
                    "(or: pip install -e '.[openjev]')"
                ) from exc

            try:
                model = wev.load(self._model_id, device=self._device)
            except Exception as exc:
                raise BackendNotAvailable(
                    f"Failed to load OpenJev model {self._model_id!r}: {exc}"
                ) from exc

            self._model = model
            return model

    async def decide(
        self,
        context: str,
        question: str,
        options: list[str],
        question_type: QuestionType,
    ) -> Decision:
        if not options:
            raise ValueError("options must be non-empty")

        model = self._ensure_loaded()

        # Build the question payload in the shape OpenJev expects.
        # Reference: https://pypi.org/project/wev-ai/
        if question_type == QuestionType.NOUL:
            typed_question: dict[str, Any] = {
                "type": "noul",
                "instructions": question,
                "criteria": {"true": "Yes", "false": "No"},
            }
        elif question_type == QuestionType.CHOICE:
            typed_question = {
                "type": "choice",
                "instructions": question,
                "criteria": {opt: opt for opt in options},
            }
        elif question_type == QuestionType.SCORE:
            typed_question = {
                "type": "score",
                "instructions": question,
                "criteria": {opt: opt for opt in options},
            }
        else:
            raise ValueError(f"unsupported question_type: {question_type!r}")

        context = truncate_context(context, self._max_context_chars)

        start_t = time.perf_counter()
        try:
            raw = await asyncio.to_thread(
                model.predict,
                state=context,
                questions={"decision": typed_question},
            )
        except Exception as exc:
            raise BackendNotAvailable(f"OpenJev inference failed: {exc}") from exc
        latency_ms = (time.perf_counter() - start_t) * 1000.0

        # OpenJev returns {"answers": {"decision": {...}}}
        answers = raw.get("answers") if isinstance(raw, dict) else None
        if not isinstance(answers, dict) or not answers:
            raise BackendNotAvailable(f"OpenJev returned no answers: {raw!r}")
        answer = answers.get("decision") or next(iter(answers.values()))
        if not isinstance(answer, dict):
            raise BackendNotAvailable(f"OpenJev returned an unexpected answer payload: {answer!r}")

        label: str | None = None
        confidence: float = 0.0
        probabilities: dict[str, float] = {}

        if question_type == QuestionType.NOUL:
            prob_true = float(answer.get("noul", 0.0))
            # `noul` is P(true). Route to yes/no based on that.
            label = "yes" if prob_true >= 0.5 else "no"
            confidence = prob_true if label == "yes" else 1.0 - prob_true
            probabilities = {"yes": prob_true, "no": 1.0 - prob_true}
        elif question_type in (QuestionType.CHOICE, QuestionType.SCORE):
            label = answer.get("choice") or answer.get("score")
            probabilities = {
                str(k): float(v) for k, v in (answer.get("probabilities") or {}).items()
            }
            if label is None and probabilities:
                label = max(probabilities, key=lambda k: probabilities[k])
            if label is not None:
                confidence = probabilities.get(str(label), 0.0)

        if label is None:
            raise BackendNotAvailable(
                f"OpenJev returned no label for {question_type.value}: {answer!r}"
            )

        # Ensure the label is one of the allowed options (case-insensitive).
        options_lower = {o.lower(): o for o in options}
        label = options_lower.get(str(label).lower(), str(label))
        if label not in options:
            raise BackendNotAvailable(f"OpenJev returned label {label!r} not in {options}")

        return Decision(
            label=label,
            confidence=float(confidence),
            scores=probabilities,
            latency_ms=latency_ms,
        )

    def unload(self) -> None:
        """Release the model (useful for tests)."""
        with self._lock:
            self._model = None
