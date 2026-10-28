"""End-to-end tests of the FastAPI application (no network, no model download)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from open_decide.api.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _simple_tree() -> dict[str, object]:
    return {
        "id": "simple",
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
                "confidence_threshold": 0.0,
            },
            "urgent": {"id": "urgent", "type": "terminal", "result": "urgent"},
            "calm": {"id": "calm", "type": "terminal", "result": "calm"},
        },
    }


# --------------------------------------------------------------------------- #
# Static / meta endpoints
# --------------------------------------------------------------------------- #


async def test_index_serves_html(client: AsyncClient) -> None:
    res = await client.get("/")
    assert res.status_code == 200
    assert "Open Decide" in res.text


async def test_list_backends(client: AsyncClient) -> None:
    res = await client.get("/api/backends")
    assert res.status_code == 200
    assert "mock" in res.json()["backends"]
    assert "tamev" in res.json()["backends"]


async def test_get_example(client: AsyncClient) -> None:
    res = await client.get("/api/examples/ticket_routing")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "ticket_routing"
    assert "triage" in data["nodes"]


async def test_get_unknown_example(client: AsyncClient) -> None:
    res = await client.get("/api/examples/does_not_exist")
    assert res.status_code == 404


# --------------------------------------------------------------------------- #
# /api/run
# --------------------------------------------------------------------------- #


async def test_run_mock(client: AsyncClient) -> None:
    res = await client.post(
        "/api/run",
        json={"tree": _simple_tree(), "input": "hello", "backend": "mock"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["result"] in {"urgent", "calm"}
    assert data["steps"] == 2
    assert len(data["path"]) == 1
    entry = data["path"][0]
    assert entry["node_id"] == "start"
    assert entry["next_node"] in {"urgent", "calm"}
    assert entry["fell_back"] is False


async def test_run_with_fallback(client: AsyncClient) -> None:
    tree = _simple_tree()
    tree["nodes"]["start"]["confidence_threshold"] = 1.0  # type: ignore[index]
    tree["nodes"]["start"]["fallback"] = "urgent"  # type: ignore[index]
    res = await client.post(
        "/api/run",
        json={"tree": tree, "input": "hello", "backend": "mock"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["result"] == "urgent"
    assert data["path"][0]["fell_back"] is True


async def test_run_invalid_tree(client: AsyncClient) -> None:
    res = await client.post(
        "/api/run",
        json={"tree": {"id": "x"}, "input": "hello", "backend": "mock"},
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["code"] == "invalid_tree"
    assert isinstance(detail["errors"], list)


async def test_run_unknown_backend(client: AsyncClient) -> None:
    res = await client.post(
        "/api/run",
        json={"tree": _simple_tree(), "input": "hello", "backend": "nope"},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "unknown_backend"


async def test_run_low_confidence_without_fallback(client: AsyncClient) -> None:
    tree = _simple_tree()
    tree["nodes"]["start"]["confidence_threshold"] = 1.0  # type: ignore[index]
    res = await client.post(
        "/api/run",
        json={"tree": tree, "input": "hello", "backend": "mock"},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "low_confidence_no_fallback"


async def test_run_backend_unavailable_returns_422(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backend that cannot be loaded must produce a 422, not a 500."""
    from open_decide.backends.base import BackendNotAvailable
    from open_decide.backends.tamev import TamevBackend

    def boom(self: TamevBackend) -> None:
        raise BackendNotAvailable("tamev extra not installed")

    monkeypatch.setattr(TamevBackend, "_ensure_loaded", boom)

    res = await client.post(
        "/api/run",
        json={"tree": _simple_tree(), "input": "hello", "backend": "tamev"},
    )
    assert res.status_code == 422
    body = res.json()
    assert body["detail"]["code"] == "backend_unavailable"
    assert "tamev" in body["detail"]["message"].lower()
