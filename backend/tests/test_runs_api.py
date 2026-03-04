import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_create_run():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/runs",
            json={
                "repo_url": "https://github.com/user/repo",
                "base_branch": "main",
                "feature_name": "add login",
                "requirements": "Add a login page with email/password",
            },
        )
    assert response.status_code == 201
    data = response.json()
    assert data["feature_name"] == "add login"
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_runs():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_run_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/runs/nonexistent")
    assert response.status_code == 404
