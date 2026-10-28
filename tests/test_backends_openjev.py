"""Tests for the OpenJev backend (lazy loading, parsing, error handling)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from open_decide.backends import get_backend
from open_decide.backends.base import BackendNotAvailable
from open_decide.backends.openjev import OpenJevBackend
from open_decide.models import QuestionType


def test_openjev_is_lazy() -> None:
    backend = get_backend("openjev")
    assert isinstance(backend, OpenJevBackend)
    assert backend._model is None


def test_openjev_registered() -> None:
    backend = get_backend("openjev", model_id="alanhuangya/OpenJev-1.7B")
    assert isinstance(backend, OpenJevBackend)


async def test_openjev_without_wev_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "wev", None)

    backend = OpenJevBackend()
    with pytest.raises(BackendNotAvailable, match=r"openjev.*extra"):
        await backend.decide("hello", "Is it urgent?", ["yes", "no"], QuestionType.NOUL)


class _FakeModel:
    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers
        self.last_kwargs: dict[str, Any] = {}

    def predict(self, **kwargs: Any) -> dict[str, Any]:
        self.last_kwargs = kwargs
        return {"answers": self._answers}


def _fake_wev_load(answers: dict[str, Any]) -> Any:
    class _FakeWev:
        @staticmethod
        def load(model_id: str, device: str = "cpu") -> _FakeModel:
            return _FakeModel(answers)

    return _FakeWev


async def test_openjev_noul_yes() -> None:
    fake = _fake_wev_load({"decision": {"type": "noul", "noul": 0.92}})
    with patch.dict("sys.modules", {"wev": fake}):
        backend = OpenJevBackend()
        decision = await backend.decide(
            "I need help now!", "Is it urgent?", ["yes", "no"], QuestionType.NOUL
        )
    assert decision.label == "yes"
    assert decision.confidence == pytest.approx(0.92)
    assert decision.scores["yes"] == pytest.approx(0.92)


async def test_openjev_noul_no() -> None:
    fake = _fake_wev_load({"decision": {"type": "noul", "noul": 0.1}})
    with patch.dict("sys.modules", {"wev": fake}):
        backend = OpenJevBackend()
        decision = await backend.decide(
            "all good", "Is it urgent?", ["yes", "no"], QuestionType.NOUL
        )
    assert decision.label == "no"
    assert decision.confidence == pytest.approx(0.9)


async def test_openjev_choice() -> None:
    fake = _fake_wev_load(
        {
            "decision": {
                "type": "choice",
                "choice": "billing",
                "probabilities": {"billing": 0.7, "technical": 0.2, "commercial": 0.1},
            }
        }
    )
    with patch.dict("sys.modules", {"wev": fake}):
        backend = OpenJevBackend()
        decision = await backend.decide(
            "I was charged twice",
            "What kind of request?",
            ["billing", "technical", "commercial"],
            QuestionType.CHOICE,
        )
    assert decision.label == "billing"
    assert decision.confidence == pytest.approx(0.7)


async def test_openjev_sends_questions_kwarg() -> None:
    fake_module = _fake_wev_load({"decision": {"type": "noul", "noul": 0.5}})
    with patch.dict("sys.modules", {"wev": fake_module}):
        backend = OpenJevBackend()
        model = backend._ensure_loaded()
        await backend.decide("x", "Is it?", ["yes", "no"], QuestionType.NOUL)
    assert "questions" in model.last_kwargs
    assert "state" in model.last_kwargs
    assert "question" not in model.last_kwargs
