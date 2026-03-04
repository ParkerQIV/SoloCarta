import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_full_api_flow():
    """Test: create run -> get run -> verify state."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create
        res = await client.post(
            "/api/runs",
            json={
                "repo_url": "/tmp/test-repo",
                "base_branch": "main",
                "feature_name": "test feature",
                "requirements": "Build a test feature",
            },
        )
        assert res.status_code == 201
        run = res.json()
        run_id = run["id"]

        # Get
        res = await client.get(f"/api/runs/{run_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "pending"

        # List
        res = await client.get("/api/runs")
        assert res.status_code == 200
        assert len(res.json()) >= 1
