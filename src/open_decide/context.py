"""Context management for decision backends.

Long inputs (emails, reports) dominate inference time because attention is
quadratic in the prefill phase. For *routing* decisions, the signal is almost
always in the first and last paragraphs (subject + signature), so we truncate
the middle.

The head/tail strategy is deliberately simple and lossless for the two ends
that matter. Callers can opt out with ``max_chars=0``.
"""

from __future__ import annotations

DEFAULT_MAX_CHARS = 4000  # ~1000 tokens for FR/EN
_HEAD_RATIO = 0.7  # 70% head, 30% tail
_SEPARATOR = "\n\n[... truncated ...]\n\n"


def truncate_context(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Truncate ``text`` to at most ``max_chars`` by keeping head + tail.

    Args:
        text: The full input.
        max_chars: Max characters to keep. ``0`` or negative disables truncation.

    Returns:
        Either ``text`` unchanged (if short or disabled) or a head+tail slice
        with a clear separator in the middle.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text

    budget = max_chars - len(_SEPARATOR)
    if budget < 100:
        # Too small for a meaningful head+tail split; just cut.
        return text[:max_chars]

    head_len = int(budget * _HEAD_RATIO)
    tail_len = budget - head_len
    return text[:head_len] + _SEPARATOR + text[-tail_len:]
