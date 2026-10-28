"""Tests for the visual editor route and its static assets."""

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


async def test_editor_serves_html(client: AsyncClient) -> None:
    res = await client.get("/editor")
    assert res.status_code == 200
    assert "Visual editor" in res.text
    assert "vis-network" in res.text
    assert "/static/editor.js" in res.text


async def test_editor_js_is_served(client: AsyncClient) -> None:
    res = await client.get("/static/editor.js")
    assert res.status_code == 200
    assert "vis.DataSet" in res.text


async def test_index_links_to_editor(client: AsyncClient) -> None:
    res = await client.get("/")
    assert res.status_code == 200
    assert 'href="/editor"' in res.text
