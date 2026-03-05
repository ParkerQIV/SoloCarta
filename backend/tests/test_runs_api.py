import pytest
from datetime import datetime, timezone
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database import async_session
from sqlalchemy import select as sa_select
from app.models import AgentOutput, PipelineRun


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


@pytest.mark.asyncio
async def test_list_outputs_empty():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create a run first
        create_resp = await client.post(
            "/api/runs",
            json={
                "repo_url": "https://github.com/user/repo",
                "feature_name": "test outputs empty",
                "requirements": "Test",
            },
        )
        run_id = create_resp.json()["id"]
        response = await client.get(f"/api/runs/{run_id}/outputs")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_outputs_after_create():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create a run
        create_resp = await client.post(
            "/api/runs",
            json={
                "repo_url": "https://github.com/user/repo",
                "feature_name": "test outputs",
                "requirements": "Test",
            },
        )
        run_id = create_resp.json()["id"]

    # Manually insert an AgentOutput
    now = datetime.now(timezone.utc)
    async with async_session() as db:
        output = AgentOutput(
            run_id=run_id,
            agent_name="pm",
            output_text="Generated spec content",
            status="completed",
            started_at=now,
            completed_at=now,
        )
        db.add(output)
        await db.commit()
        await db.refresh(output)
        output_id = output.id

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/runs/{run_id}/outputs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == output_id
    assert data[0]["agent_name"] == "pm"
    assert data[0]["output_text"] == "Generated spec content"
    assert data[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_get_diff_run_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/runs/nonexistent/diff")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_diff_no_sandbox():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/api/runs",
            json={
                "repo_url": "https://github.com/user/repo",
                "feature_name": "test diff no sandbox",
                "requirements": "Test",
            },
        )
        run_id = create_resp.json()["id"]
        response = await client.get(f"/api/runs/{run_id}/diff")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_diff_sandbox_missing():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/api/runs",
            json={
                "repo_url": "https://github.com/user/repo",
                "feature_name": "test diff sandbox missing",
                "requirements": "Test",
            },
        )
        run_id = create_resp.json()["id"]

    # Set sandbox_path to a non-existent directory
    async with async_session() as db:
        result = await db.execute(
            sa_select(PipelineRun).where(PipelineRun.id == run_id)
        )
        run = result.scalar_one()
        run.sandbox_path = "/tmp/nonexistent_sandbox_path_xyz"
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/runs/{run_id}/diff")
    assert response.status_code == 410
