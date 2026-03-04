"""LangGraph orchestrator — sequential pipeline with conditional gate."""

from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END


class PipelineState(TypedDict):
    run_id: str
    repo_url: str
    base_branch: str
    sandbox_path: str
    feature_name: str
    requirements: str

    # Agent outputs
    spec: str | None
    architecture: str | None
    plan: str | None
    implementation_summary: str | None
    qa_results: dict | None
    review_report: str | None
    gate_result: dict | None

    # Control
    current_step: str
    status: str
    error: str | None


def sandbox_setup_node(state: PipelineState) -> dict:
    """Create sandbox workspace."""
    from app.engine.sandbox import create_sandbox
    from app.config import settings

    sandbox_path = create_sandbox(
        repo_path=state["repo_url"],  # Will be local path for now
        workspace_dir=settings.workspaces_dir,
        run_id=state["run_id"],
        branch_name=f"ai/{state['feature_name'].replace(' ', '-')}",
        base_branch=state["base_branch"],
    )
    return {"sandbox_path": sandbox_path, "current_step": "pm", "status": "running"}


def pm_node(state: PipelineState) -> dict:
    """Run PM agent to generate spec."""
    import anyio
    from app.engine.claude_runtime import run_agent, AgentRole

    context = f"""Feature: {state['feature_name']}

Requirements:
{state['requirements']}

Generate a specification for this feature."""

    spec = anyio.from_thread.run(
        run_agent, AgentRole.PM, state["sandbox_path"], context
    )
    return {"spec": spec, "current_step": "architect"}


def architect_node(state: PipelineState) -> dict:
    """Run Architect agent."""
    import anyio
    from app.engine.claude_runtime import run_agent, AgentRole

    context = f"""Specification:
{state['spec']}

Generate architecture notes for this feature."""

    architecture = anyio.from_thread.run(
        run_agent, AgentRole.ARCHITECT, state["sandbox_path"], context
    )
    return {"architecture": architecture, "current_step": "planner"}


def planner_node(state: PipelineState) -> dict:
    """Run Planner agent."""
    import anyio
    from app.engine.claude_runtime import run_agent, AgentRole

    context = f"""Specification:
{state['spec']}

Architecture:
{state['architecture']}

Create an ordered task plan."""

    plan = anyio.from_thread.run(
        run_agent, AgentRole.PLANNER, state["sandbox_path"], context
    )
    return {"plan": plan, "current_step": "dev"}


def dev_node(state: PipelineState) -> dict:
    """Run Dev agent."""
    import anyio
    from app.engine.claude_runtime import run_agent, AgentRole

    context = f"""Specification:
{state['spec']}

Architecture:
{state['architecture']}

Plan:
{state['plan']}

Implement the feature according to this plan."""

    summary = anyio.from_thread.run(
        run_agent, AgentRole.DEV, state["sandbox_path"], context
    )
    return {"implementation_summary": summary, "current_step": "qa"}


def qa_node(state: PipelineState) -> dict:
    """Run QA agent."""
    import anyio
    from app.engine.claude_runtime import run_agent, AgentRole

    context = f"""Specification:
{state['spec']}

Run lint, tests, and type checking. Report all results."""

    results_text = anyio.from_thread.run(
        run_agent, AgentRole.QA, state["sandbox_path"], context
    )
    return {
        "qa_results": {"raw_output": results_text},
        "current_step": "reviewer",
    }


def reviewer_node(state: PipelineState) -> dict:
    """Run Reviewer agent."""
    import anyio
    from app.engine.claude_runtime import run_agent, AgentRole

    context = f"""Specification:
{state['spec']}

Architecture:
{state['architecture']}

QA Results:
{state['qa_results']}

Review the implementation."""

    report = anyio.from_thread.run(
        run_agent, AgentRole.REVIEWER, state["sandbox_path"], context
    )
    return {"review_report": report, "current_step": "gatekeeper"}


def gatekeeper_node(state: PipelineState) -> dict:
    """Run Gatekeeper agent."""
    import anyio
    import json
    from app.engine.claude_runtime import run_agent, AgentRole

    context = f"""Specification:
{state['spec']}

Architecture:
{state['architecture']}

QA Results:
{state['qa_results']}

Reviewer Report:
{state['review_report']}

Score and decide PASS/FAIL."""

    result_text = anyio.from_thread.run(
        run_agent, AgentRole.GATEKEEPER, state["sandbox_path"], context
    )
    try:
        gate_result = json.loads(result_text)
    except json.JSONDecodeError:
        gate_result = {
            "decision": "FAIL",
            "reasons": ["Failed to parse gatekeeper output"],
        }

    return {"gate_result": gate_result, "current_step": "done"}


def route_gate_result(state: PipelineState) -> Literal["create_pr", "fail"]:
    """Route based on gatekeeper decision."""
    gate = state.get("gate_result", {})
    if gate.get("decision") == "PASS":
        return "create_pr"
    return "fail"


def create_pr_node(state: PipelineState) -> dict:
    """Create PR on GitHub."""
    # TODO: implement GitHub integration in Task 8
    return {"status": "passed"}


def fail_node(state: PipelineState) -> dict:
    """Handle pipeline failure."""
    return {"status": "failed"}


def build_pipeline_graph():
    """Build and compile the LangGraph pipeline."""
    builder = StateGraph(PipelineState)

    # Add nodes
    builder.add_node("sandbox_setup", sandbox_setup_node)
    builder.add_node("pm", pm_node)
    builder.add_node("architect", architect_node)
    builder.add_node("planner", planner_node)
    builder.add_node("dev", dev_node)
    builder.add_node("qa", qa_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("gatekeeper", gatekeeper_node)
    builder.add_node("create_pr", create_pr_node)
    builder.add_node("fail", fail_node)

    # Sequential edges
    builder.add_edge(START, "sandbox_setup")
    builder.add_edge("sandbox_setup", "pm")
    builder.add_edge("pm", "architect")
    builder.add_edge("architect", "planner")
    builder.add_edge("planner", "dev")
    builder.add_edge("dev", "qa")
    builder.add_edge("qa", "reviewer")
    builder.add_edge("reviewer", "gatekeeper")

    # Conditional edge after gatekeeper
    builder.add_conditional_edges("gatekeeper", route_gate_result)

    builder.add_edge("create_pr", END)
    builder.add_edge("fail", END)

    return builder.compile()
