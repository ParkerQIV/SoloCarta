import pytest
from app.engine.orchestrator import build_pipeline_graph, PipelineState, parse_gate_json


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


def test_parse_gate_json_from_markdown_fences():
    result = parse_gate_json('```json\n{"decision": "PASS", "score": 9}\n```')
    assert result["decision"] == "PASS"
    assert result["score"] == 9


def test_parse_gate_json_raw():
    result = parse_gate_json('{"decision": "FAIL", "reasons": ["tests failed"]}')
    assert result["decision"] == "FAIL"
    assert result["reasons"] == ["tests failed"]


def test_parse_gate_json_with_surrounding_text():
    text = 'Here is my analysis:\n\n```json\n{"decision": "PASS", "score": 8}\n```\n\nOverall looks good.'
    result = parse_gate_json(text)
    assert result["decision"] == "PASS"


def test_parse_gate_json_unparseable():
    result = parse_gate_json("totally not json at all")
    assert result["decision"] == "FAIL"
    assert "Failed to parse" in result["reasons"][0]
