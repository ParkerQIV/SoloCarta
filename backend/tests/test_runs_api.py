import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select as sa_select
from app.main import app
from app.database import async_session
from app.models import PipelineRun


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
async def test_sandbox_path_saved_after_pipeline():
    """Verify sandbox_path is persisted to PipelineRun after update."""
    async with async_session() as db:
        run = PipelineRun(
            repo_url="/tmp/fake-repo",
            feature_name="test sandbox save",
            requirements="Test",
            sandbox_path=None,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    async with async_session() as db:
        result = await db.execute(
            sa_select(PipelineRun).where(PipelineRun.id == run_id)
        )
        r = result.scalar_one()
        r.sandbox_path = "/tmp/test-sandbox"
        await db.commit()

    async with async_session() as db:
        result = await db.execute(
            sa_select(PipelineRun).where(PipelineRun.id == run_id)
        )
        r = result.scalar_one()
        assert r.sandbox_path == "/tmp/test-sandbox"


@pytest.mark.asyncio
async def test_create_run_invalid_repo_url_traversal():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/runs",
            json={
                "repo_url": "../../../etc/passwd",
                "feature_name": "evil",
                "requirements": "hack",
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_run_invalid_repo_url_empty():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/runs",
            json={
                "repo_url": "",
                "feature_name": "test",
                "requirements": "test",
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_run_valid_local_path():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/runs",
            json={
                "repo_url": "/Users/test/my-repo",
                "feature_name": "valid local",
                "requirements": "test",
            },
        )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_cancel_run_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/runs/nonexistent/cancel")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_run_not_running():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/api/runs",
            json={
                "repo_url": "/tmp/test-repo",
                "feature_name": "test cancel",
                "requirements": "Test",
            },
        )
        run_id = create_resp.json()["id"]
        response = await client.post(f"/api/runs/{run_id}/cancel")
    assert response.status_code == 400
    assert "not running" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_outcome_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/runs/nonexistent/outcome")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_outcome_after_create():
    from app.models import OutcomeLog
    async with async_session() as db:
        run = PipelineRun(
            repo_url="/tmp/test",
            feature_name="test outcome",
            requirements="test",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        outcome = OutcomeLog(
            run_id=run.id,
            total_duration_seconds=30.5,
            agent_durations={"pm": 10.0, "dev": 15.0},
            gate_scores={"criteria_met": 3},
            failure_agent=None,
            failure_category=None,
            failure_summary=None,
        )
        db.add(outcome)
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/runs/{run.id}/outcome")
    assert response.status_code == 200
    data = response.json()
    assert data["total_duration_seconds"] == 30.5
    assert data["agent_durations"]["pm"] == 10.0
    assert data["failure_agent"] is None


@pytest.mark.asyncio
async def test_get_stats():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_runs" in data
    assert "pass_rate" in data
    assert "avg_gate_score" in data
    assert "most_common_failure_agent" in data
