import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.models import PipelineRun, AgentOutput
from app.engine.runner import execute_pipeline

router = APIRouter(prefix="/api/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    repo_url: str
    base_branch: str = "main"
    feature_name: str
    requirements: str


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


class AgentOutputResponse(BaseModel):
    id: str
    run_id: str
    agent_name: str
    output_text: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


@router.get("/{run_id}/outputs", response_model=list[AgentOutputResponse])
async def list_outputs(
    run_id: str,
    agent_name: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentOutput).where(AgentOutput.run_id == run_id)
    if agent_name:
        query = query.where(AgentOutput.agent_name == agent_name)
    query = query.order_by(AgentOutput.started_at)
    result = await db.execute(query)
    return result.scalars().all()


class DiffResponse(BaseModel):
    diff: str
    has_changes: bool


@router.get("/{run_id}/diff", response_model=DiffResponse)
async def get_diff(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineRun).where(PipelineRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.sandbox_path:
        raise HTTPException(status_code=400, detail="No sandbox for this run")

    sandbox = Path(run.sandbox_path)
    if not sandbox.exists():
        raise HTTPException(status_code=410, detail="Sandbox has been cleaned up")

    try:
        proc = subprocess.run(
            ["git", "diff", f"{run.base_branch}...HEAD"],
            cwd=str(sandbox),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"git diff failed: {proc.stderr.strip()}",
            )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="git diff timed out")

    diff_text = proc.stdout
    return DiffResponse(diff=diff_text, has_changes=len(diff_text.strip()) > 0)
