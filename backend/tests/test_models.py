import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models import Base, PipelineRun, AgentOutput
from datetime import datetime, timezone


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_pipeline_run(db):
    run = PipelineRun(
        repo_url="https://github.com/user/repo",
        base_branch="main",
        feature_name="add login",
        requirements="Add a login page",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    assert run.id is not None
    assert run.status == "pending"
    assert run.repo_url == "https://github.com/user/repo"


def test_create_agent_output(db):
    run = PipelineRun(
        repo_url="https://github.com/user/repo",
        base_branch="main",
        feature_name="add login",
        requirements="Add a login page",
    )
    db.add(run)
    db.commit()

    output = AgentOutput(
        run_id=run.id,
        agent_name="pm",
        output_text="Spec: ...",
        status="completed",
    )
    db.add(output)
    db.commit()
    db.refresh(output)

    assert output.id is not None
    assert output.run_id == run.id
    assert output.agent_name == "pm"


def test_agent_output_error_field(db):
    run = PipelineRun(
        repo_url="/tmp/test",
        feature_name="test error field",
        requirements="test",
    )
    db.add(run)
    db.commit()

    output = AgentOutput(
        run_id=run.id,
        agent_name="pm",
        output_text="",
        status="error",
        error="Agent timed out after 300s",
    )
    db.add(output)
    db.commit()
    db.refresh(output)
    assert output.error == "Agent timed out after 300s"


def test_create_outcome_log(db):
    run = PipelineRun(
        repo_url="/tmp/test",
        feature_name="test outcome",
        requirements="test",
    )
    db.add(run)
    db.commit()

    from app.models import OutcomeLog
    outcome = OutcomeLog(
        run_id=run.id,
        total_duration_seconds=45.2,
        agent_durations={"pm": 12.3, "architect": 8.1},
        gate_scores={"criteria_met": 3, "tests_pass": 2},
        failure_agent=None,
        failure_category=None,
        failure_summary=None,
    )
    db.add(outcome)
    db.commit()
    db.refresh(outcome)
    assert outcome.id is not None
    assert outcome.total_duration_seconds == 45.2
    assert outcome.agent_durations["pm"] == 12.3
    assert outcome.failure_agent is None
