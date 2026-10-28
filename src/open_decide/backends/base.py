"""Abstract interface for decision backends.

A backend answers a typed question over a given context and returns a
``Decision``. It must:

- always return a ``Decision`` whose ``label`` is one of the provided options,
- be as deterministic as possible given a fixed context and question.

Implementations are expected to be fast (sub-100 ms) and cheap, unlike a
generative LLM.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from open_decide.models import Decision, QuestionType


class BackendError(Exception):
    """Base class for backend-level errors."""


class BackendNotAvailable(BackendError):
    """Raised when a backend cannot be loaded.

    Typical causes: the optional extras are not installed (e.g. ``torch`` for
    TAMEV), the model cannot be downloaded, or the checkpoint does not expose
    the expected interface.
    """


class DecisionBackend(ABC):
    """Interface every decision backend must implement."""

    name: ClassVar[str] = "abstract"

    @abstractmethod
    async def decide(
        self,
        context: str,
        question: str,
        options: list[str],
        question_type: QuestionType,
    ) -> Decision:
        """Answer ``question`` over ``context``.

        Args:
            context: The raw input the tree is running on (text for now).
            question: The prompt of the current decision node.
            options: The list of allowed labels. Must be non-empty.
            question_type: The kind of decision (noul / choice / score).

        Returns:
            A ``Decision`` whose ``label`` is in ``options``.
        """
