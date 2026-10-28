"""TAMEV backend: fast, CPU-friendly decision model.

Wraps ``Tamkimd/tamev-micro-minilm`` (Apache-2.0, 22.8M params) via
``transformers`` with ``trust_remote_code=True``.

The model is loaded lazily on first use so that importing this module does
not require ``torch`` / ``transformers``. Only instantiating the backend does.

Reference:
    https://huggingface.co/Tamkimd/tamev-micro-minilm
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, ClassVar

from open_decide.backends.base import BackendNotAvailable, DecisionBackend
from open_decide.context import DEFAULT_MAX_CHARS, truncate_context
from open_decide.models import Decision, QuestionType

_DEFAULT_MODEL_ID = "Tamkimd/tamev-micro-minilm"


class TamevBackend(DecisionBackend):
    """Decision backend backed by a TAMEV model.

    Args:
        model_id: Hugging Face model id. Defaults to the Micro tier
            (22.8M params, CPU-friendly, Apache-2.0).
        device: Torch device string. Defaults to ``"cpu"`` because TAMEV is
            designed to run well on CPU (7.3 ms p50 on one thread).
    """

    name: ClassVar[str] = "tamev"

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
        self._tokenizer: Any | None = None
        self._model: Any | None = None
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> tuple[Any, Any]:
        if self._model is not None and self._tokenizer is not None:
            return self._model, self._tokenizer

        with self._lock:
            if self._model is not None and self._tokenizer is not None:
                return self._model, self._tokenizer

            try:
                import torch  # noqa: F401
                from transformers import (
                    AutoModel,
                    AutoTokenizer,
                )
            except ImportError as exc:
                raise BackendNotAvailable(
                    "TamevBackend requires the 'tamev' extra. "
                    "Install it with: uv sync --extra tamev "
                    "(or: pip install -e '.[tamev]')"
                ) from exc

            try:
                tokenizer = AutoTokenizer.from_pretrained(self._model_id, trust_remote_code=True)
                model = AutoModel.from_pretrained(self._model_id, trust_remote_code=True)
            except Exception as exc:
                raise BackendNotAvailable(
                    f"Failed to load TAMEV model {self._model_id!r}: {exc}"
                ) from exc

            if not hasattr(model, "predict_decision"):
                raise BackendNotAvailable(
                    f"model {self._model_id!r} does not expose "
                    "predict_decision(); is it a TAMEV checkpoint?"
                )

            model.to(self._device)
            model.eval()

            self._tokenizer = tokenizer
            self._model = model
            return model, tokenizer

    async def decide(
        self,
        context: str,
        question: str,
        options: list[str],
        question_type: QuestionType,
    ) -> Decision:
        if not options:
            raise ValueError("options must be non-empty")

        model, tokenizer = self._ensure_loaded()
        context = truncate_context(context, self._max_context_chars)

        start = time.perf_counter()
        raw = await asyncio.to_thread(
            model.predict_decision,
            state=context,
            question=question,
            options=options,
            tokenizer=tokenizer,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        label = raw.get("best_option") or raw.get("label")
        probabilities = raw.get("probabilities") or {}
        confidence = raw.get("confidence")

        if label is None and probabilities:
            label = max(probabilities, key=lambda k: probabilities[k])
        if label is None:
            raise RuntimeError(f"TAMEV returned no decision: keys={sorted(raw)}")
        if confidence is None:
            confidence = probabilities.get(label, 0.0)

        return Decision(
            label=str(label),
            confidence=float(confidence),
            scores={k: float(v) for k, v in probabilities.items()},
            latency_ms=latency_ms,
        )

    def unload(self) -> None:
        """Release the model (useful for tests)."""
        with self._lock:
            self._model = None
            self._tokenizer = None
