import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, field_validator

from datetime import datetime

from app.database import get_db
from app.models import PipelineRun, AgentOutput, OutcomeLog
from app.engine.runner import execute_pipeline

router = APIRouter(prefix="/api/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    repo_url: str
    base_branch: str = "main"
    feature_name: str
    requirements: str

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("repo_url must not be empty")
        if ".." in v:
            raise ValueError("repo_url must not contain '..'")
        if v.startswith("https://"):
            return v
        if v.startswith("/"):
            return v
        raise ValueError("repo_url must be an absolute path or https:// URL")


class RunResponse(BaseModel):
    id: str
    repo_url: str
    base_branch: str
    feature_name: str
    requirements: str
    status: str
    current_step: str | None
    gate_score: int | None
    gate_decision: str | None
    error: str | None
    pr_url: str | None

    model_config = {"from_attributes": True}


@router.post("", status_code=201, response_model=RunResponse)
async def create_run(req: CreateRunRequest, db: AsyncSession = Depends(get_db)):
    run = PipelineRun(
        repo_url=req.repo_url,
        base_branch=req.base_branch,
        feature_name=req.feature_name,
        requirements=req.requirements,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


@router.get("", response_model=list[RunResponse])
async def list_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineRun).order_by(PipelineRun.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineRun).where(PipelineRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/{run_id}/start", status_code=202)
async def start_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineRun).where(PipelineRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "pending":
        raise HTTPException(status_code=400, detail="Run already started")

    asyncio.create_task(execute_pipeline(run_id))
    return {"message": "Pipeline started", "run_id": run_id}


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineRun).where(PipelineRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "running":
        raise HTTPException(status_code=400, detail="Run is not running")

    from app.engine.runner import request_cancellation
    cancelled = request_cancellation(run_id)
    if cancelled:
        run.status = "cancelled"
        await db.commit()
    return {"message": "Cancellation requested", "run_id": run_id}


class AgentOutputResponse(BaseModel):
    id: str
    run_id: str
    agent_name: str
    output_text: str
    status: str
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


@router.get("/{run_id}/outputs", response_model=list[AgentOutputResponse])
async def list_outputs(
    run_id: str,
    agent_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentOutput).where(AgentOutput.run_id == run_id)
    if agent_name:
        query = query.where(AgentOutput.agent_name == agent_name)
    query = query.order_by(AgentOutput.started_at)
    result = await db.execute(query)
    return result.scalars().all()


class OutcomeResponse(BaseModel):
    id: str
    run_id: str
    total_duration_seconds: float | None
    agent_durations: dict | None
    gate_scores: dict | None
    failure_agent: str | None
    failure_category: str | None
    failure_summary: str | None

    model_config = {"from_attributes": True}


@router.get("/{run_id}/outcome", response_model=OutcomeResponse)
async def get_outcome(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OutcomeLog).where(OutcomeLog.run_id == run_id)
    )
    outcome = result.scalar_one_or_none()
    if not outcome:
        raise HTTPException(status_code=404, detail="Outcome not found")
    return outcome


stats_router = APIRouter(prefix="/api", tags=["stats"])


class StatsResponse(BaseModel):
    total_runs: int
    passed: int
    failed: int
    errored: int
    pass_rate: float
    avg_gate_score: float | None
    most_common_failure_agent: str | None


@stats_router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    all_runs = await db.execute(select(PipelineRun))
    runs = all_runs.scalars().all()

    total = len(runs)
    passed = sum(1 for r in runs if r.status == "passed")
    failed = sum(1 for r in runs if r.status == "failed")
    errored = sum(1 for r in runs if r.status == "error")
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    scores = [r.gate_score for r in runs if r.gate_score is not None]
    avg_score = sum(scores) / len(scores) if scores else None

    # Most common failure agent from OutcomeLog
    outcome_result = await db.execute(
        select(OutcomeLog.failure_agent)
        .where(OutcomeLog.failure_agent.isnot(None))
    )
    failure_agents = [r[0] for r in outcome_result.all()]
    most_common = max(set(failure_agents), key=failure_agents.count) if failure_agents else None

    return StatsResponse(
        total_runs=total,
        passed=passed,
        failed=failed,
        errored=errored,
        pass_rate=round(pass_rate, 1),
        avg_gate_score=round(avg_score, 1) if avg_score is not None else None,
        most_common_failure_agent=most_common,
    )
