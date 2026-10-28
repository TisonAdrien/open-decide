"""End-to-end tests of the execution engine using deterministic backends."""

from __future__ import annotations

import pytest

from open_decide.backends.base import DecisionBackend
from open_decide.backends.mock import MockBackend
from open_decide.engine import (
    DecisionEngine,
    InvalidBackendAnswer,
    LowConfidenceNoFallback,
    MaxStepsExceeded,
)
from open_decide.models import (
    Decision,
    DecisionTree,
    QuestionType,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class _StubBackend(DecisionBackend):
    """Deterministic backend for unit tests: always returns the same answer."""

    name = "stub"

    def __init__(self, label: str, confidence: float) -> None:
        self._label = label
        self._confidence = confidence

    async def decide(
        self,
        context: str,
        question: str,
        options: list[str],
        question_type: QuestionType,
    ) -> Decision:
        return Decision(label=self._label, confidence=self._confidence)


def _simple_tree(threshold: float = 0.5, fallback: str | None = None) -> DecisionTree:
    return DecisionTree.model_validate(
        {
            "id": "t",
            "name": "Simple",
            "root": "start",
            "nodes": {
                "start": {
                    "id": "start",
                    "type": "decision",
                    "question_type": "noul",
                    "prompt": "Is it urgent?",
                    "options": [
                        {"label": "yes", "next": "urgent"},
                        {"label": "no", "next": "calm"},
                    ],
                    "confidence_threshold": threshold,
                    "fallback": fallback,
                },
                "urgent": {"id": "urgent", "type": "terminal", "result": "urgent"},
                "calm": {"id": "calm", "type": "terminal", "result": "calm"},
                "review": {"id": "review", "type": "terminal", "result": "manual_review"},
            },
        }
    )


def _cyclic_tree() -> DecisionTree:
    return DecisionTree.model_validate(
        {
            "id": "loop",
            "name": "Loop",
            "root": "loop",
            "nodes": {
                "loop": {
                    "id": "loop",
                    "type": "decision",
                    "question_type": "choice",
                    "prompt": "Again?",
                    "options": [
                        {"label": "a", "next": "loop"},
                        {"label": "b", "next": "loop"},
                    ],
                    "confidence_threshold": 0.0,
                },
            },
        }
    )


# --------------------------------------------------------------------------- #
# Nominal path
# --------------------------------------------------------------------------- #


async def test_nominal_path_with_mock_backend() -> None:
    backend = MockBackend(keywords={"urgent": "yes"})
    engine = DecisionEngine(backend)
    tree = _simple_tree(threshold=0.5)

    result = await engine.run(tree, "this is urgent, please help")

    assert result.result == "urgent"
    assert result.steps == 2
    assert len(result.path) == 1
    entry = result.path[0]
    assert entry.node_id == "start"
    assert entry.decision.label == "yes"
    assert entry.next_node == "urgent"
    assert entry.fell_back is False


async def test_nominal_path_no_match() -> None:
    backend = MockBackend(keywords={"urgent": "yes"})
    engine = DecisionEngine(backend)
    tree = _simple_tree(threshold=0.0)

    result = await engine.run(tree, "a calm request")

    assert result.result in {"urgent", "calm"}
    assert result.steps == 2


# --------------------------------------------------------------------------- #
# Fallback
# --------------------------------------------------------------------------- #


async def test_low_confidence_routes_to_fallback() -> None:
    backend = _StubBackend(label="yes", confidence=0.3)
    engine = DecisionEngine(backend)
    tree = _simple_tree(threshold=0.8, fallback="review")

    result = await engine.run(tree, "ambiguous")

    assert result.result == "manual_review"
    assert len(result.path) == 1
    assert result.path[0].fell_back is True
    assert result.path[0].next_node == "review"


async def test_low_confidence_without_fallback_raises() -> None:
    backend = _StubBackend(label="yes", confidence=0.2)
    engine = DecisionEngine(backend)
    tree = _simple_tree(threshold=0.8, fallback=None)

    with pytest.raises(LowConfidenceNoFallback):
        await engine.run(tree, "ambiguous")


# --------------------------------------------------------------------------- #
# Invalid backend answers
# --------------------------------------------------------------------------- #


async def test_invalid_label_raises() -> None:
    backend = _StubBackend(label="maybe", confidence=0.99)
    engine = DecisionEngine(backend)
    tree = _simple_tree(threshold=0.0)

    with pytest.raises(InvalidBackendAnswer):
        await engine.run(tree, "whatever")


# --------------------------------------------------------------------------- #
# Cycle guard
# --------------------------------------------------------------------------- #


async def test_max_steps_guard() -> None:
    backend = _StubBackend(label="a", confidence=1.0)
    engine = DecisionEngine(backend, max_steps=5)

    with pytest.raises(MaxStepsExceeded):
        await engine.run(_cyclic_tree(), "loop forever")
