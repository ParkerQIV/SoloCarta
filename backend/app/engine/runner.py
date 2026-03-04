import asyncio
import traceback
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import async_session
from app.models import PipelineRun, AgentOutput
from app.engine.orchestrator import build_pipeline_graph, PipelineState
from app.routers.stream import publish_event


async def execute_pipeline(run_id: str) -> None:
    """Execute the full pipeline for a run. Runs as a background task."""
    async with async_session() as db:
        result = await db.execute(
            select(PipelineRun).where(PipelineRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            return

        run.status = "running"
        await db.commit()
        publish_event(run_id, "status", {"status": "running"})

        try:
            graph = build_pipeline_graph()
            initial_state: PipelineState = {
                "run_id": run.id,
                "repo_url": run.repo_url,
                "base_branch": run.base_branch,
                "sandbox_path": "",
                "feature_name": run.feature_name,
                "requirements": run.requirements,
                "spec": None,
                "architecture": None,
                "plan": None,
                "implementation_summary": None,
                "qa_results": None,
                "review_report": None,
                "gate_result": None,
                "current_step": "pending",
                "status": "pending",
                "error": None,
            }

            # Run the graph
            final_state = await asyncio.to_thread(graph.invoke, initial_state)

            # Update DB with results
            run.status = final_state["status"]
            run.current_step = final_state["current_step"]
            if final_state.get("gate_result"):
                run.gate_score = final_state["gate_result"].get("total_score")
                run.gate_decision = final_state["gate_result"].get("decision")

            await db.commit()
            publish_event(run_id, "pipeline_complete", {
                "status": final_state["status"],
                "gate_result": final_state.get("gate_result"),
            })

        except Exception as e:
            run.status = "error"
            run.error = traceback.format_exc()
            await db.commit()
            publish_event(run_id, "pipeline_complete", {
                "status": "error",
                "error": str(e),
            })
