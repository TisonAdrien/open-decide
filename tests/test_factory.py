import pytest

from open_decide.backends import clear_backend_cache, get_backend
from open_decide.backends.mock import MockBackend
from open_decide.backends.tamev import TamevBackend


def test_get_mock() -> None:
    backend = get_backend("mock")
    assert isinstance(backend, MockBackend)


def test_get_mock_with_kwargs() -> None:
    backend = get_backend("mock", keywords={"urgent": "yes"})
    assert isinstance(backend, MockBackend)


def test_get_tamev_is_lazy() -> None:
    """Instantiating the TAMEV backend must not load the model."""
    backend = get_backend("tamev")
    assert isinstance(backend, TamevBackend)
    assert backend._model is None  # type: ignore[attr-defined]
    assert backend._tokenizer is None  # type: ignore[attr-defined]


def test_get_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown backend"):
        get_backend("nope")


def test_get_backend_returns_cached_instance() -> None:
    """Two calls with the same name+kwargs must return the same instance."""
    clear_backend_cache()
    a = get_backend("mock", keywords={"x": "yes"})
    b = get_backend("mock", keywords={"x": "yes"})
    assert a is b


def test_get_backend_different_kwargs_different_instance() -> None:
    clear_backend_cache()
    a = get_backend("mock", keywords={"x": "yes"})
    b = get_backend("mock", keywords={"x": "no"})
    assert a is not b


def test_freeze_is_order_stable_for_dicts() -> None:
    """_freeze must produce the same hashable form regardless of dict order."""
    from open_decide.backends import _freeze

    a = _freeze({"a": 1, "b": {"c": 2, "d": 3}})
    b = _freeze({"b": {"d": 3, "c": 2}, "a": 1})
    assert a == b
    assert hash(a) == hash(b)


def test_freeze_handles_nested_lists_and_sets() -> None:
    from open_decide.backends import _freeze

    a = _freeze({"k": [1, 2, {"x": "y"}], "s": {3, 1, 2}})
    b = _freeze({"s": {2, 3, 1}, "k": [1, 2, {"x": "y"}]})
    assert a == b


def test_clear_backend_cache() -> None:
    clear_backend_cache()
    a = get_backend("mock")
    clear_backend_cache()
    b = get_backend("mock")
    assert a is not b
