import pytest
from pydantic import ValidationError

from open_decide.models import DecisionTree


def _minimal_tree(**overrides):
    base = {
        "id": "t1",
        "name": "Test",
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
            },
            "urgent": {"id": "urgent", "type": "terminal", "result": "urgent"},
            "calm": {"id": "calm", "type": "terminal", "result": "calm"},
        },
    }
    base.update(overrides)
    return base


def test_valid_tree() -> None:
    tree = DecisionTree.model_validate(_minimal_tree())
    assert tree.get_node("start").type == "decision"


def test_unknown_root() -> None:
    with pytest.raises(ValidationError):
        DecisionTree.model_validate(_minimal_tree(root="nope"))


def test_unknown_next_reference() -> None:
    data = _minimal_tree()
    data["nodes"]["start"]["options"][0]["next"] = "ghost"
    with pytest.raises(ValidationError):
        DecisionTree.model_validate(data)


def test_noul_requires_yes_no() -> None:
    data = _minimal_tree()
    data["nodes"]["start"]["options"] = [
        {"label": "maybe", "next": "urgent"},
        {"label": "nope", "next": "calm"},
    ]
    with pytest.raises(ValidationError):
        DecisionTree.model_validate(data)


def test_duplicate_option_labels() -> None:
    data = _minimal_tree()
    data["nodes"]["start"]["options"] = [
        {"label": "yes", "next": "urgent"},
        {"label": "yes", "next": "calm"},
    ]
    with pytest.raises(ValidationError):
        DecisionTree.model_validate(data)
