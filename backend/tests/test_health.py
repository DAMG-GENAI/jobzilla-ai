"""Tests for health check and core API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_root(client):
    """Test root endpoint returns API info."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "KillMatch API"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_health(client):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_ready(client):
    """Test readiness check endpoint."""
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True


@pytest.mark.asyncio
async def test_docs_available(client):
    """Test that API docs are accessible."""
    response = await client.get("/docs")
    assert response.status_code == 200
