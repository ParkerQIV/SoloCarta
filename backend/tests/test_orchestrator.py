import pytest
from app.engine.orchestrator import build_pipeline_graph, PipelineState


def test_pipeline_state_defaults():
    state = PipelineState(
        run_id="test-1",
        repo_url="https://github.com/user/repo",
        base_branch="main",
        sandbox_path="/tmp/sandbox",
        feature_name="test feature",
        requirements="do something",
        current_step="pending",
        status="pending",
    )
    assert state["run_id"] == "test-1"
    assert state["status"] == "pending"
    assert state.get("spec") is None


def test_build_pipeline_graph():
    graph = build_pipeline_graph()
    assert graph is not None
    # Graph should be compiled and invocable
    assert hasattr(graph, "invoke")
