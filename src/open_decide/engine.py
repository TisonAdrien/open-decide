"""Execution engine for decision trees.

The engine walks a ``DecisionTree`` from its root to a terminal node. At each
``DecisionNode`` it asks the configured ``DecisionBackend`` for a typed answer,
validates it, and routes to the next node based on the answer and the node's
``confidence_threshold``.

Design notes:

- The engine is agnostic of the backend: any ``DecisionBackend`` works.
- The engine never trusts the backend blindly: an answer whose label is not
  one of the node's options is rejected with ``InvalidBackendAnswer``.
- When confidence falls below the node's threshold, the engine follows the
  node's ``fallback`` if one is defined, otherwise raises
  ``LowConfidenceNoFallback``. This is deliberate: silent routing on a shaky
  decision is worse than failing loudly.
- Cycles are allowed in the schema but guarded at runtime by ``max_steps``.
"""

from __future__ import annotations

from open_decide.backends.base import DecisionBackend
from open_decide.models import (
    DecisionNode,
    DecisionTree,
    RunResult,
    TerminalNode,
    TraceEntry,
)

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class EngineError(Exception):
    """Base class for all engine errors."""


class MaxStepsExceeded(EngineError):
    """Raised when the engine exceeds its ``max_steps`` budget."""


class InvalidBackendAnswer(EngineError):
    """Raised when a backend returns a label that is not a valid option."""


class LowConfidenceNoFallback(EngineError):
    """Raised when confidence is below threshold and no fallback is defined."""


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #


class DecisionEngine:
    """Run a ``DecisionTree`` over a context using a ``DecisionBackend``."""

    def __init__(self, backend: DecisionBackend, *, max_steps: int = 200) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        self._backend = backend
        self._max_steps = max_steps

    async def run(self, tree: DecisionTree, context: str) -> RunResult:
        """Execute ``tree`` on ``context`` and return the result and trace."""
        path: list[TraceEntry] = []
        node_id = tree.root
        steps = 0

        while True:
            steps += 1
            if steps > self._max_steps:
                raise MaxStepsExceeded(f"tree {tree.id!r} exceeded max_steps={self._max_steps}")

            node = tree.get_node(node_id)

            if isinstance(node, TerminalNode):
                return RunResult(
                    tree_id=tree.id,
                    input=context,
                    path=path,
                    result=node.result,
                    steps=steps,
                )

            if not isinstance(node, DecisionNode):
                # Defensive: the schema forbids this, but stay explicit.
                raise EngineError(f"node {node_id!r} is neither a decision nor a terminal node")

            options = node.option_labels()
            decision = await self._backend.decide(
                context=context,
                question=node.prompt,
                options=options,
                question_type=node.question_type,
            )

            if decision.label not in options:
                raise InvalidBackendAnswer(
                    f"node {node.id!r}: backend returned label "
                    f"{decision.label!r} which is not in {options}"
                )

            if decision.confidence < node.confidence_threshold:
                if node.fallback is None:
                    raise LowConfidenceNoFallback(
                        f"node {node.id!r}: confidence "
                        f"{decision.confidence:.3f} < threshold "
                        f"{node.confidence_threshold:.3f} and no fallback "
                        f"is defined"
                    )
                next_node = node.fallback
                fell_back = True
            else:
                next_node = next(opt.next for opt in node.options if opt.label == decision.label)
                fell_back = False

            path.append(
                TraceEntry(
                    node_id=node.id,
                    question=node.prompt,
                    options=options,
                    decision=decision,
                    next_node=next_node,
                    fell_back=fell_back,
                )
            )
            node_id = next_node
