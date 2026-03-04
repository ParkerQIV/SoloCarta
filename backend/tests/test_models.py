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
