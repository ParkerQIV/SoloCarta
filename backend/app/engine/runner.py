import asyncio
import json
import traceback
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import async_session
from app.models import PipelineRun, AgentOutput
from app.engine.orchestrator import build_pipeline_graph, PipelineState
from app.routers.stream import publish_event

AGENT_NODES = {"pm", "architect", "planner", "dev", "qa", "reviewer", "gatekeeper"}
ORDERED_STEPS = ["sandbox_setup", "pm", "architect", "planner", "dev", "qa", "reviewer", "gatekeeper"]

_NODE_OUTPUT_KEYS = {
    "pm": "spec",
    "architect": "architecture",
    "planner": "plan",
    "dev": "implementation_summary",
    "qa": "qa_results",
    "reviewer": "review_report",
    "gatekeeper": "gate_result",
}


async def _save_agent_output(
    run_id: str,
    agent_name: str,
    output_text: str,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> str:
    """Save an AgentOutput record and return its id."""
    async with async_session() as db:
        record = AgentOutput(
            run_id=run_id,
            agent_name=agent_name,
            output_text=output_text,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record.id


def _run_graph_streaming(graph, initial_state: PipelineState, run_id: str) -> dict:
    """Run the graph with streaming, saving outputs and emitting SSE events per node."""
    import anyio

    total_steps = len(ORDERED_STEPS)
    node_started_at: dict[str, datetime] = {}
    merged_state = dict(initial_state)

    for chunk in graph.stream(initial_state, stream_mode="updates"):
        node_name = list(chunk.keys())[0]
        update = chunk[node_name]

        # Merge update into our tracked state
        merged_state.update(update)

        # Emit agent_start for the *next* step based on current_step in the update
        next_step = update.get("current_step")
        if next_step and next_step in AGENT_NODES and next_step not in node_started_at:
            node_started_at[next_step] = datetime.now(timezone.utc)
            step_index = ORDERED_STEPS.index(next_step) if next_step in ORDERED_STEPS else -1
            publish_event(run_id, "agent_start", {
                "agent": next_step,
                "step_index": step_index,
                "total_steps": total_steps,
            })

        # Save output for agent nodes that just completed
        if node_name in AGENT_NODES:
            output_key = _NODE_OUTPUT_KEYS.get(node_name)
            raw_output = update.get(output_key) if output_key else None
            if raw_output is not None:
                output_text = raw_output if isinstance(raw_output, str) else json.dumps(raw_output)
            else:
                output_text = ""

            completed_at = datetime.now(timezone.utc)
            started_at = node_started_at.get(node_name)
            step_index = ORDERED_STEPS.index(node_name) if node_name in ORDERED_STEPS else -1

            output_id = anyio.from_thread.run(
                _save_agent_output, run_id, node_name, output_text, started_at, completed_at
            )

            publish_event(run_id, "agent_complete", {
                "agent": node_name,
                "step_index": step_index,
                "total_steps": total_steps,
                "output_id": output_id,
            })

    return merged_state


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
                "pr_url": None,
            }

            # Run the graph with streaming
            final_state = await asyncio.to_thread(
                _run_graph_streaming, graph, initial_state, run_id
            )

            # Update DB with results
            run.status = final_state["status"]
            run.current_step = final_state["current_step"]
            if final_state.get("gate_result"):
                run.gate_score = final_state["gate_result"].get("total_score")
                run.gate_decision = final_state["gate_result"].get("decision")
            if final_state.get("pr_url"):
                run.pr_url = final_state["pr_url"]

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
