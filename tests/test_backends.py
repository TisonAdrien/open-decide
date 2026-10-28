import pytest

from open_decide.backends.mock import MockBackend
from open_decide.models import QuestionType


async def test_mock_is_deterministic() -> None:
    backend = MockBackend()
    d1 = await backend.decide("hello world", "Is it a greeting?", ["yes", "no"], QuestionType.NOUL)
    d2 = await backend.decide("hello world", "Is it a greeting?", ["yes", "no"], QuestionType.NOUL)
    assert d1.label == d2.label
    assert d1.confidence == d2.confidence


async def test_mock_keyword_override() -> None:
    backend = MockBackend(keywords={"urgent": "yes"})
    d = await backend.decide("this is urgent!", "Is it urgent?", ["yes", "no"], QuestionType.NOUL)
    assert d.label == "yes"
    assert d.confidence >= 0.9


async def test_mock_scores_sum_to_one() -> None:
    backend = MockBackend()
    d = await backend.decide("something", "Pick one", ["a", "b", "c"], QuestionType.CHOICE)
    assert d.label in {"a", "b", "c"}
    assert abs(sum(d.scores.values()) - 1.0) < 1e-9


async def test_tamev_raises_backend_not_available(monkeypatch) -> None:
    """Simulate torch/transformers being absent."""
    import sys

    from open_decide.backends.base import BackendNotAvailable
    from open_decide.backends.tamev import TamevBackend

    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "transformers", None)

    backend = TamevBackend()
    with pytest.raises(BackendNotAvailable, match=r"tamev.*extra"):
        await backend.decide("ctx", "q", ["a", "b"], QuestionType.CHOICE)
