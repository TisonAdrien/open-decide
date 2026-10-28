"""API tests for the ingestion endpoints."""

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


async def test_ingest_txt(client: AsyncClient) -> None:
    res = await client.post(
        "/api/ingest",
        files={"file": ("note.txt", b"hello world", "text/plain")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["text"] == "hello world"
    assert body["chars"] == 11


async def test_ingest_unsupported(client: AsyncClient) -> None:
    res = await client.post(
        "/api/ingest",
        files={"file": ("movie.mp4", b"\x00\x01", "video/mp4")},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "unsupported_file_type"


async def test_ingest_empty_file(client: AsyncClient) -> None:
    res = await client.post(
        "/api/ingest",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "ingestion_failed"


async def test_run_file_with_txt(client: AsyncClient) -> None:
    import json as _json

    res = await client.post(
        "/api/run-file",
        data={
            "tree": _json.dumps(_simple_tree()),
            "backend": "mock",
            "max_steps": "200",
        },
        files={"file": ("note.txt", b"urgent message", "text/plain")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["result"] in {"urgent", "calm"}
    assert body["steps"] == 2


async def test_run_file_with_input_text(client: AsyncClient) -> None:
    import json as _json

    res = await client.post(
        "/api/run-file",
        data={
            "tree": _json.dumps(_simple_tree()),
            "backend": "mock",
            "max_steps": "200",
            "input_text": "hello",
        },
    )
    assert res.status_code == 200
    assert res.json()["steps"] == 2


async def test_run_file_missing_input(client: AsyncClient) -> None:
    import json as _json

    res = await client.post(
        "/api/run-file",
        data={
            "tree": _json.dumps(_simple_tree()),
            "backend": "mock",
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "missing_input"


async def test_run_file_invalid_tree_json(client: AsyncClient) -> None:
    res = await client.post(
        "/api/run-file",
        data={"tree": "not json", "backend": "mock", "input_text": "x"},
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "invalid_tree_json"


async def test_extract_txt(client: AsyncClient) -> None:
    res = await client.post(
        "/api/extract",
        files={
            "file": (
                "note.txt",
                b"Invoice INV-42, total 1 234,56 EUR, due 28/10/2026. Contact: bob@example.com",
                "text/plain",
            )
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["fields"]["amounts"][0]["value"] == 1234.56
    assert "2026-10-28" in body["fields"]["dates"]
    assert "bob@example.com" in body["fields"]["emails"]
