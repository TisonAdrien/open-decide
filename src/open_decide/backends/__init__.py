"""Decision backends registry with singleton caching.

``get_backend(name, **kwargs)`` returns a cached instance keyed by
``(name, sorted(kwargs.items()))``. This means:

- Two requests asking for ``"tamev"`` with the same kwargs share the same
  backend instance, hence the same in-memory model (no reload).
- Asking for ``"tamev"`` with a different ``model_id`` creates a distinct
  instance, as expected.

The cache lives for the lifetime of the process. Under ``uvicorn --reload``,
the process restarts on file changes and the cache is cleared, which is the
desired behaviour for development.
"""

from __future__ import annotations

import threading
from typing import Any

from open_decide.backends.base import (
    BackendError,
    BackendNotAvailable,
    DecisionBackend,
)
from open_decide.backends.cascade import CascadeBackend
from open_decide.backends.mock import MockBackend
from open_decide.backends.openjev import OpenJevBackend
from open_decide.backends.tamev import TamevBackend

_BACKENDS: dict[str, type[DecisionBackend]] = {
    "mock": MockBackend,
    "tamev": TamevBackend,
    "openjev": OpenJevBackend,
    "cascade": CascadeBackend,
}

# Cache: (name, frozen kwargs) -> backend instance
_CACHE: dict[tuple[str, tuple[tuple[str, Any], ...]], DecisionBackend] = {}
_CACHE_LOCK = threading.Lock()


def _freeze(value: Any) -> Any:
    """Recursively convert a value to a hashable, order-stable form."""
    if isinstance(value, dict):
        return tuple(
            sorted(
                ((k, _freeze(v)) for k, v in value.items()),
                key=lambda kv: str(kv[0]),
            )
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(v) for v in value), key=repr))
    try:
        hash(value)
        return value
    except TypeError:
        return repr(value)


def get_backend(name: str, **kwargs: Any) -> DecisionBackend:
    """Return a cached backend instance, creating it on first call.

    Args:
        name: One of ``"mock"``, ``"tamev"`` or ``"openjev"``.
        **kwargs: Forwarded to the backend constructor on first creation.

    Raises:
        ValueError: If ``name`` is unknown.
    """
    try:
        cls = _BACKENDS[name]
    except KeyError as exc:
        raise ValueError(f"unknown backend {name!r}; available: {sorted(_BACKENDS)}") from exc

    key = (name, _freeze(kwargs))

    # Fast path: instance already cached.
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    # Slow path: create under lock, double-check to avoid double creation.
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            return cached
        instance = cls(**kwargs)
        _CACHE[key] = instance
        return instance


def list_cached_backends() -> list[DecisionBackend]:
    """Return the list of currently cached backend instances."""
    with _CACHE_LOCK:
        return list(_CACHE.values())


def clear_backend_cache() -> None:
    """Drop all cached backends (useful in tests and for explicit reload)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def preload_backend(name: str, **kwargs: Any) -> DecisionBackend:
    """Create and cache a backend *and* force its model to load now.

    Use this from a startup hook to pay the model-loading cost once, before
    the first user request, instead of on the first request.
    """
    backend = get_backend(name, **kwargs)
    # Trigger lazy load if the backend exposes the hook.
    ensure = getattr(backend, "_ensure_loaded", None)
    if callable(ensure):
        ensure()
    return backend


__all__ = [
    "BackendError",
    "BackendNotAvailable",
    "CascadeBackend",
    "DecisionBackend",
    "MockBackend",
    "OpenJevBackend",
    "TamevBackend",
    "clear_backend_cache",
    "get_backend",
    "list_cached_backends",
    "preload_backend",
]
