import asyncio
import traceback
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import async_session
from app.models import PipelineRun, AgentOutput
from app.engine.orchestrator import build_pipeline_graph, PipelineState
from app.routers.stream import publish_event


# Cancellation registry: run_id -> Event
_cancel_events: dict[str, asyncio.Event] = {}


def request_cancellation(run_id: str) -> bool:
    """Request cancellation of a running pipeline. Returns True if event was set."""
    event = _cancel_events.get(run_id)
    if event:
        event.set()
        return True
    return False


def is_cancelled(run_id: str) -> bool:
    """Check if a run has been cancelled."""
    event = _cancel_events.get(run_id)
    return event.is_set() if event else False


async def _save_agent_output(
    run_id: str,
    agent_name: str,
    output_text: str,
    started_at: datetime | None,
    completed_at: datetime | None,
    status: str = "completed",
    error: str | None = None,
) -> str:
    """Save an AgentOutput record and return its id."""
    async with async_session() as db:
        record = AgentOutput(
            run_id=run_id,
            agent_name=agent_name,
            output_text=output_text,
            status=status,
            error=error,
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record.id


async def _save_outcome(
    run_id: str,
    total_duration_seconds: float | None,
    agent_durations: dict | None,
    gate_scores: dict | None,
    failure_agent: str | None = None,
    failure_category: str | None = None,
    failure_summary: str | None = None,
) -> None:
    """Save an OutcomeLog record for a completed pipeline run."""
    from app.models import OutcomeLog
    async with async_session() as db:
        record = OutcomeLog(
            run_id=run_id,
            total_duration_seconds=total_duration_seconds,
            agent_durations=agent_durations,
            gate_scores=gate_scores,
            failure_agent=failure_agent,
            failure_category=failure_category,
            failure_summary=failure_summary,
        )
        db.add(record)
        await db.commit()


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
        pipeline_start = datetime.now(timezone.utc)

        cancel_event = asyncio.Event()
        _cancel_events[run_id] = cancel_event

        sandbox_path = ""
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

            # Run the graph
            final_state = await asyncio.to_thread(graph.invoke, initial_state)

            sandbox_path = final_state.get("sandbox_path", "")

            # Handle cancellation
            if final_state.get("status") == "cancelled" or cancel_event.is_set():
                run.status = "cancelled"
                run.sandbox_path = sandbox_path or None
                await db.commit()
                publish_event(run_id, "pipeline_complete", {"status": "cancelled"})
                return

            # Update DB with results
            run.status = final_state["status"]
            run.current_step = final_state["current_step"]
            run.sandbox_path = sandbox_path or None
            if final_state.get("gate_result"):
                run.gate_score = final_state["gate_result"].get("total_score")
                run.gate_decision = final_state["gate_result"].get("decision")
            if final_state.get("pr_url"):
                run.pr_url = final_state["pr_url"]

            await db.commit()

            # Save outcome log
            duration = (datetime.now(timezone.utc) - pipeline_start).total_seconds()
            agent_durations = {}
            async with async_session() as outcome_db:
                agent_result = await outcome_db.execute(
                    select(AgentOutput).where(AgentOutput.run_id == run_id)
                )
                for ao in agent_result.scalars():
                    if ao.started_at and ao.completed_at:
                        agent_durations[ao.agent_name] = (ao.completed_at - ao.started_at).total_seconds()

            gate = final_state.get("gate_result") or {}
            await _save_outcome(
                run_id=run_id,
                total_duration_seconds=duration,
                agent_durations=agent_durations,
                gate_scores={k: v for k, v in gate.items() if k != "decision" and k != "reasons"},
                failure_agent=None,
                failure_category="gate_fail" if final_state["status"] == "failed" else None,
                failure_summary=None if final_state["status"] != "failed" else "Gatekeeper rejected",
            )

            publish_event(run_id, "pipeline_complete", {
                "status": final_state["status"],
                "gate_result": final_state.get("gate_result"),
            })

        except Exception as e:
            # If it's an AgentError, save the per-agent error record
            from app.engine.resilience import AgentError
            if isinstance(e, AgentError):
                now = datetime.now(timezone.utc)
                await _save_agent_output(
                    run_id=run_id,
                    agent_name=e.agent_name,
                    output_text="",
                    started_at=now,
                    completed_at=now,
                    status="error",
                    error=str(e.original_error),
                )

            run.status = "error"
            run.error = traceback.format_exc()
            run.sandbox_path = sandbox_path or None
            await db.commit()

            # Save outcome log for errors
            duration = (datetime.now(timezone.utc) - pipeline_start).total_seconds()
            fail_agent = None
            fail_category = "crash"
            if isinstance(e, AgentError):
                fail_agent = e.agent_name
                fail_category = "timeout" if isinstance(e.original_error, (TimeoutError, asyncio.TimeoutError)) else "crash"
            await _save_outcome(
                run_id=run_id,
                total_duration_seconds=duration,
                agent_durations={},
                gate_scores=None,
                failure_agent=fail_agent,
                failure_category=fail_category,
                failure_summary=str(e),
            )

            publish_event(run_id, "pipeline_complete", {
                "status": "error",
                "error": str(e),
            })
        finally:
            _cancel_events.pop(run_id, None)
