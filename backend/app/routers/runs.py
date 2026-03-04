from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.models import PipelineRun

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
