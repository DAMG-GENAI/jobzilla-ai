"""Tests for Job Market MCP Server."""

import pytest
from httpx import ASGITransport, AsyncClient
from server import app


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    """Test health check."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_docs(client):
    """Test API docs accessible."""
    response = await client.get("/docs")
    assert response.status_code == 200
