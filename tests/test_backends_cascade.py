"""Tests for the cascade backend."""

from __future__ import annotations

from typing import Any

import pytest

from open_decide.backends.base import DecisionBackend
from open_decide.backends.cascade import CascadeBackend
from open_decide.models import Decision, QuestionType


class _StubBackend(DecisionBackend):
    name = "stub"

    def __init__(self, label: str, confidence: float) -> None:
        self._label = label
        self._confidence = confidence
        self.calls = 0

    async def decide(
        self,
        context: str,
        question: str,
        options: list[str],
        question_type: QuestionType,
    ) -> Decision:
        self.calls += 1
        return Decision(label=self._label, confidence=self._confidence)


@pytest.fixture
def patch_get_backend(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace get_backend so the cascade uses our stubs."""
    import open_decide.backends as backend_pkg

    stubs: dict[str, _StubBackend] = {}

    def fake_get_backend(name: str, **kwargs: Any) -> _StubBackend:
        if name not in stubs:
            raise AssertionError(f"stub {name} not preloaded")
        return stubs[name]

    monkeypatch.setattr(backend_pkg, "get_backend", fake_get_backend)
    return stubs


async def test_cascade_uses_fast_when_confident(
    patch_get_backend: dict[str, _StubBackend],
) -> None:
    fast = _StubBackend("yes", 0.9)
    accurate = _StubBackend("no", 0.5)
    patch_get_backend["tamev"] = fast
    patch_get_backend["openjev"] = accurate

    cascade = CascadeBackend(fast="tamev", accurate="openjev", threshold=0.75)
    decision = await cascade.decide("x", "Q", ["yes", "no"], QuestionType.NOUL)

    assert decision.label == "yes"
    assert decision.escalated is False
    assert fast.calls == 1
    assert accurate.calls == 0


async def test_cascade_escalates_on_low_confidence(
    patch_get_backend: dict[str, _StubBackend],
) -> None:
    fast = _StubBackend("yes", 0.4)
    accurate = _StubBackend("no", 0.95)
    patch_get_backend["tamev"] = fast
    patch_get_backend["openjev"] = accurate

    cascade = CascadeBackend(fast="tamev", accurate="openjev", threshold=0.75)
    decision = await cascade.decide("x", "Q", ["yes", "no"], QuestionType.NOUL)

    assert decision.label == "no"
    assert decision.escalated is True
    assert decision.fast_confidence == 0.4
    assert fast.calls == 1
    assert accurate.calls == 1
