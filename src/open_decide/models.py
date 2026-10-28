"""Pydantic schema for decision trees, decisions and traces.

The schema is intentionally small and strict. It is the contract between the
no-code editor, the execution engine and the decision backends.

A tree is composed of two node types:

- ``DecisionNode`` asks a typed question (noul / choice / score) to a decision
  backend and routes to one of its options.
- ``TerminalNode`` is a leaf and carries the final result label.

Cycles are allowed by the schema (some workflows need loops); the engine will
guard them at runtime with a ``max_steps`` limit.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

# --------------------------------------------------------------------------- #
# Questions
# --------------------------------------------------------------------------- #


class QuestionType(StrEnum):
    """Kind of decision to ask a backend."""

    NOUL = "noul"  # yes / no
    CHOICE = "choice"  # one among N
    SCORE = "score"  # ordinal scale, ordered labels


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #


class Option(BaseModel):
    """An outgoing branch of a decision node."""

    model_config = {"frozen": True}

    label: str = Field(..., min_length=1)
    next: str = Field(..., min_length=1)


class DecisionNode(BaseModel):
    """A node that asks a typed question and routes based on the answer."""

    model_config = {"frozen": True}

    id: str = Field(..., min_length=1)
    type: Literal["decision"] = "decision"
    question_type: QuestionType
    prompt: str = Field(..., min_length=1)
    options: list[Option] = Field(..., min_length=2)
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    fallback: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _check_options(self) -> DecisionNode:
        labels = [o.label for o in self.options]

        if len(set(labels)) != len(labels):
            raise ValueError(f"node {self.id!r}: duplicate option labels {labels}")

        if self.question_type == QuestionType.NOUL and set(labels) != {"yes", "no"}:
            raise ValueError(
                f"node {self.id!r}: a noul node must have exactly the "
                f"options 'yes' and 'no', got {labels}"
            )

        if self.question_type == QuestionType.CHOICE and len(labels) < 2:
            raise ValueError(f"node {self.id!r}: a choice node needs at least 2 options")

        if self.question_type == QuestionType.SCORE and not 2 <= len(labels) <= 10:
            raise ValueError(f"node {self.id!r}: a score node needs 2 to 10 options")

        return self

    def option_labels(self) -> list[str]:
        return [o.label for o in self.options]


class TerminalNode(BaseModel):
    """A leaf carrying the final result label."""

    model_config = {"frozen": True}

    id: str = Field(..., min_length=1)
    type: Literal["terminal"] = "terminal"
    result: str = Field(..., min_length=1)
    description: str | None = None


Node = Annotated[
    DecisionNode | TerminalNode,
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------- #
# Tree
# --------------------------------------------------------------------------- #


class DecisionTree(BaseModel):
    """A complete decision tree."""

    model_config = {"frozen": True}

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = Field(default="0.1.0")
    description: str | None = None
    root: str = Field(..., min_length=1)
    nodes: dict[str, Node]

    @model_validator(mode="after")
    def _check_references(self) -> DecisionTree:
        if self.root not in self.nodes:
            raise ValueError(f"root {self.root!r} not found among nodes {sorted(self.nodes)}")

        for node_id, node in self.nodes.items():
            if node.type != "decision":
                continue

            for opt in node.options:
                if opt.next not in self.nodes:
                    raise ValueError(
                        f"node {node_id!r}: option {opt.label!r} points to "
                        f"unknown node {opt.next!r}"
                    )

            if node.fallback is not None and node.fallback not in self.nodes:
                raise ValueError(
                    f"node {node_id!r}: fallback points to unknown node {node.fallback!r}"
                )

        return self

    def get_node(self, node_id: str) -> Node:
        return self.nodes[node_id]


# --------------------------------------------------------------------------- #
# Decisions and traces
# --------------------------------------------------------------------------- #


class Decision(BaseModel):
    """Result returned by a decision backend for a single question."""

    model_config = {"frozen": True}

    label: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    scores: dict[str, float] = Field(default_factory=dict)
    latency_ms: float | None = None
    escalated: bool = False
    fast_confidence: float | None = None


class TraceEntry(BaseModel):
    """A single hop in an execution trace."""

    model_config = {"frozen": True}

    node_id: str
    question: str
    options: list[str]
    decision: Decision
    next_node: str | None = None
    fell_back: bool = False


class RunResult(BaseModel):
    """The complete result of running a tree on an input."""

    model_config = {"frozen": True}

    tree_id: str
    input: str
    path: list[TraceEntry]
    result: str
    steps: int
