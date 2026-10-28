"""Optional integration tests for the TAMEV backend.

These are skipped unless both conditions are met:

1. the 'tamev' extra is installed (torch + transformers), and
2. the environment variable OPEN_DECIDE_TEST_TAMEV=1 is set.

The model is ~90 MB to download, so we don't run these by default.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("torch")
pytest.importorskip("transformers")

from open_decide.backends.tamev import TamevBackend
from open_decide.models import QuestionType

pytestmark = pytest.mark.skipif(
    os.environ.get("OPEN_DECIDE_TEST_TAMEV") != "1",
    reason="set OPEN_DECIDE_TEST_TAMEV=1 to run TAMEV integration tests",
)


@pytest.fixture(scope="module")
def backend() -> TamevBackend:
    b = TamevBackend()
    yield b
    b.unload()


async def test_choice(backend: TamevBackend) -> None:
    decision = await backend.decide(
        context="My card was blocked while I was travelling in Tokyo.",
        question="Which service queue should handle this incident?",
        options=[
            "verify_travel_unblock",
            "file_fraud_dispute",
            "branch_appointment",
        ],
        question_type=QuestionType.CHOICE,
    )
    assert decision.label in {
        "verify_travel_unblock",
        "file_fraud_dispute",
        "branch_appointment",
    }
    assert 0.0 <= decision.confidence <= 1.0
    assert abs(sum(decision.scores.values()) - 1.0) < 1e-6


async def test_noul(backend: TamevBackend) -> None:
    decision = await backend.decide(
        context="This is an emergency, I need help now!",
        question="Is this urgent?",
        options=["yes", "no"],
        question_type=QuestionType.NOUL,
    )
    assert decision.label in {"yes", "no"}


async def test_score(backend: TamevBackend) -> None:
    decision = await backend.decide(
        context="Minor cosmetic issue on the packaging.",
        question="How severe is this issue?",
        options=["low", "medium", "high"],
        question_type=QuestionType.SCORE,
    )
    assert decision.label in {"low", "medium", "high"}
