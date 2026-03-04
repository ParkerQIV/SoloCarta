# SoloCarta MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a self-improving AI development team platform with a FastAPI backend, React dashboard, and LangGraph-orchestrated agent pipeline.

**Architecture:** FastAPI serves REST + SSE endpoints. LangGraph orchestrates a sequential pipeline of 7 AI agents (PM → Architect → Planner → Dev → QA → Reviewer → Gatekeeper) running via Claude Agent SDK in sandboxed repo copies. React dashboard provides real-time pipeline visibility.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, Claude Agent SDK (`claude-agent-sdk`), SQLAlchemy + SQLite, React 18, Vite, TypeScript, TailwindCSS

---

## Task 1: Project Scaffolding — Backend

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/tests/__init__.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "solocarta"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy>=2.0.0",
    "aiosqlite>=0.20.0",
    "langgraph>=1.0.0",
    "claude-agent-sdk>=0.1.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "sse-starlette>=2.0.0",
    "pygithub>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

**Step 2: Create config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./solocarta.db"
    anthropic_api_key: str = ""
    github_token: str = ""
    workspaces_dir: str = ".workspaces"

    model_config = {"env_prefix": "SOLOCARTA_"}


settings = Settings()
```

**Step 3: Create main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="SoloCarta", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 4: Create __init__.py files**

Empty files for `backend/app/__init__.py` and `backend/tests/__init__.py`.

**Step 5: Install dependencies and verify**

Run: `cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`

**Step 6: Write smoke test**

Create `backend/tests/test_health.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

**Step 7: Run test**

Run: `cd backend && python -m pytest tests/test_health.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add backend/
git commit -m "feat: scaffold backend with FastAPI, config, and health endpoint"
```

---

## Task 2: Database Models + Setup

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models.py`
- Create: `backend/tests/test_models.py`

**Step 1: Write test for models**

Create `backend/tests/test_models.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL — models don't exist yet

**Step 3: Implement database.py**

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

**Step 4: Implement models.py**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    repo_url: Mapped[str] = mapped_column(String, nullable=False)
    base_branch: Mapped[str] = mapped_column(String, default="main")
    feature_name: Mapped[str] = mapped_column(String, nullable=False)
    requirements: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    current_step: Mapped[str | None] = mapped_column(String, nullable=True)
    sandbox_path: Mapped[str | None] = mapped_column(String, nullable=True)
    gate_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gate_decision: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    outputs: Mapped[list["AgentOutput"]] = relationship(back_populates="run")


class AgentOutput(Base):
    __tablename__ = "agent_outputs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    output_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    run: Mapped["PipelineRun"] = relationship(back_populates="outputs")
```

**Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: PASS

**Step 6: Wire DB init into FastAPI lifespan**

Update `backend/app/main.py` to add lifespan:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="SoloCarta", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Step 7: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

**Step 8: Commit**

```bash
git add backend/app/database.py backend/app/models.py backend/tests/test_models.py backend/app/main.py
git commit -m "feat: add database models for PipelineRun and AgentOutput"
```

---

## Task 3: Sandbox Engine

**Files:**
- Create: `backend/app/engine/sandbox.py`
- Create: `backend/app/engine/__init__.py`
- Create: `backend/tests/test_sandbox.py`

**Step 1: Write test for sandbox creation**

Create `backend/tests/test_sandbox.py`:

```python
import os
import tempfile
import pytest
from pathlib import Path
from app.engine.sandbox import create_sandbox, cleanup_sandbox


@pytest.fixture
def fake_repo():
    """Create a fake git repo to sandbox."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir) / "test-repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Test")
        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text("print('hello')")
        # Init git
        os.system(f"cd {repo} && git init && git add . && git commit -m 'init'")
        yield repo


def test_create_sandbox(fake_repo, tmp_path):
    workspace_dir = tmp_path / ".workspaces"
    sandbox_path = create_sandbox(
        repo_path=str(fake_repo),
        workspace_dir=str(workspace_dir),
        run_id="test-run-1",
        branch_name="ai/test-feature",
        base_branch="master",
    )

    assert Path(sandbox_path).exists()
    assert (Path(sandbox_path) / "README.md").exists()
    assert (Path(sandbox_path) / "src" / "main.py").exists()
    assert (Path(sandbox_path) / ".git").exists()


def test_cleanup_sandbox(fake_repo, tmp_path):
    workspace_dir = tmp_path / ".workspaces"
    sandbox_path = create_sandbox(
        repo_path=str(fake_repo),
        workspace_dir=str(workspace_dir),
        run_id="test-run-2",
        branch_name="ai/test-feature",
        base_branch="master",
    )
    assert Path(sandbox_path).exists()

    cleanup_sandbox(sandbox_path)
    assert not Path(sandbox_path).exists()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_sandbox.py -v`
Expected: FAIL — module doesn't exist

**Step 3: Implement sandbox.py**

```python
import shutil
import subprocess
from pathlib import Path


EXCLUDE_DIRS = {".venv", ".workspaces", "__pycache__", "node_modules", ".tox"}


def create_sandbox(
    repo_path: str,
    workspace_dir: str,
    run_id: str,
    branch_name: str,
    base_branch: str = "main",
) -> str:
    """Copy a repo into an isolated sandbox workspace and checkout a new branch."""
    src = Path(repo_path)
    dest = Path(workspace_dir) / run_id
    dest.mkdir(parents=True, exist_ok=True)

    # Copy repo contents (excluding heavy dirs)
    for item in src.iterdir():
        if item.name in EXCLUDE_DIRS:
            continue
        if item.name == ".git":
            # Copy .git separately to preserve history
            shutil.copytree(item, dest / ".git")
            continue
        if item.is_dir():
            shutil.copytree(item, dest / item.name)
        else:
            shutil.copy2(item, dest / item.name)

    # Checkout base branch, then create new branch
    subprocess.run(
        ["git", "checkout", base_branch],
        cwd=str(dest),
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=str(dest),
        capture_output=True,
        check=True,
    )

    return str(dest)


def cleanup_sandbox(sandbox_path: str) -> None:
    """Remove a sandbox workspace."""
    path = Path(sandbox_path)
    if path.exists():
        shutil.rmtree(path)
```

Create `backend/app/engine/__init__.py` (empty file).

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_sandbox.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/engine/
git add backend/tests/test_sandbox.py
git commit -m "feat: add sandbox engine for isolated workspace creation"
```

---

## Task 4: Claude Runtime Wrapper

**Files:**
- Create: `backend/app/engine/claude_runtime.py`
- Create: `backend/tests/test_claude_runtime.py`

**Step 1: Write test for runtime wrapper**

Create `backend/tests/test_claude_runtime.py`:

```python
import pytest
from app.engine.claude_runtime import build_agent_options, AgentRole


def test_build_agent_options_pm():
    options = build_agent_options(
        role=AgentRole.PM,
        sandbox_path="/tmp/sandbox",
    )
    assert options is not None
    assert "pm" in str(options.agents)


def test_build_agent_options_dev():
    options = build_agent_options(
        role=AgentRole.DEV,
        sandbox_path="/tmp/sandbox",
    )
    assert options is not None
    # Dev agent should have write/bash tools
    dev_agent = options.agents["dev"]
    assert "Bash" in dev_agent.tools
    assert "Write" in dev_agent.tools
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_claude_runtime.py -v`
Expected: FAIL

**Step 3: Implement claude_runtime.py**

```python
from enum import Enum
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions
from pathlib import Path


class AgentRole(str, Enum):
    PM = "pm"
    ARCHITECT = "architect"
    PLANNER = "planner"
    DEV = "dev"
    QA = "qa"
    REVIEWER = "reviewer"
    GATEKEEPER = "gatekeeper"


# Tools available per agent role
AGENT_TOOLS: dict[AgentRole, list[str]] = {
    AgentRole.PM: ["Read", "Glob", "Grep"],
    AgentRole.ARCHITECT: ["Read", "Glob", "Grep"],
    AgentRole.PLANNER: ["Read", "Glob", "Grep"],
    AgentRole.DEV: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    AgentRole.QA: ["Read", "Bash", "Glob", "Grep"],
    AgentRole.REVIEWER: ["Read", "Glob", "Grep"],
    AgentRole.GATEKEEPER: ["Read", "Glob", "Grep"],
}


def _load_prompt(role: AgentRole) -> str:
    """Load agent prompt template from prompts/ directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{role.value}.md"
    if prompt_path.exists():
        return prompt_path.read_text()
    return f"You are a {role.value} agent. Complete your assigned task."


def build_agent_options(
    role: AgentRole,
    sandbox_path: str,
) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions for a specific agent role."""
    prompt = _load_prompt(role)
    tools = AGENT_TOOLS[role]

    return ClaudeAgentOptions(
        agents={
            role.value: AgentDefinition(
                description=f"SoloCarta {role.value} agent",
                prompt=prompt,
                tools=tools,
                model="sonnet",
            )
        },
    )


async def run_agent(
    role: AgentRole,
    sandbox_path: str,
    context: str,
) -> str:
    """Run an agent with the given context and return its output."""
    from claude_agent_sdk import query, AssistantMessage, TextBlock, ResultMessage

    options = build_agent_options(role=role, sandbox_path=sandbox_path)

    output_parts: list[str] = []
    async for message in query(prompt=context, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    output_parts.append(block.text)

    return "\n".join(output_parts)
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_claude_runtime.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/engine/claude_runtime.py backend/tests/test_claude_runtime.py
git commit -m "feat: add Claude Agent SDK runtime wrapper with role-based tool config"
```

---

## Task 5: Agent Prompt Templates

**Files:**
- Create: `backend/app/prompts/pm.md`
- Create: `backend/app/prompts/architect.md`
- Create: `backend/app/prompts/planner.md`
- Create: `backend/app/prompts/dev.md`
- Create: `backend/app/prompts/qa.md`
- Create: `backend/app/prompts/reviewer.md`
- Create: `backend/app/prompts/gatekeeper.md`

**Step 1: Create PM prompt**

```markdown
# PM Agent

You are a Product Manager agent. Your job is to convert feature requirements into a clear specification.

## Input
You will receive:
- Feature name
- Raw requirements/context

## Output
Produce a structured specification with:

### Scope
What this feature does and does not include.

### Acceptance Criteria
Numbered list of testable criteria that define "done".

### Edge Cases
List scenarios that could cause issues.

### Constraints & Assumptions
Technical or business constraints to be aware of.

## Rules
- Be specific and testable in acceptance criteria
- Do not suggest implementation details
- Focus on WHAT, not HOW
- Keep scope tight — YAGNI
```

**Step 2: Create Architect prompt**

```markdown
# Architect Agent

You are a Software Architect agent. Your job is to determine the technical approach for implementing a specification.

## Input
You will receive:
- The specification from the PM agent
- Project conventions and existing codebase structure

## Output
Produce architecture notes covering:

### API Changes
New or modified endpoints, methods, signatures.

### Data Model Changes
New tables, columns, schema modifications, migrations needed.

### File Changes
Which existing files need modification, which new files to create.

### Risks
Technical risks, performance concerns, security considerations.

## Rules
- Work within existing project conventions
- Prefer minimal changes over rewrites
- Identify breaking changes explicitly
- Do not write implementation code
```

**Step 3: Create Planner prompt**

```markdown
# Planner Agent

You are a Planning agent. Your job is to break architecture into ordered implementation tasks.

## Input
You will receive:
- The specification
- The architecture notes

## Output
Produce a task plan:

### Tasks
Numbered, ordered list of implementation tasks. Each task must have:
- **Description**: What to do
- **Files**: Which files to create or modify
- **Done criteria**: How to verify the task is complete
- **Dependencies**: Which prior tasks must be done first

## Rules
- Tasks should be small (15-30 minutes of work each)
- Include test tasks for each implementation task
- Order tasks so dependencies come first
- Include a final integration test task
```

**Step 4: Create Dev prompt**

```markdown
# Dev Agent

You are a Developer agent. Your job is to implement code changes according to a plan.

## Input
You will receive:
- The specification
- The architecture notes
- The task plan
- Project conventions

## Actions
- Implement code changes in the repository
- Write or update tests
- Run linting and tests after implementation
- Fix any failures

## Output
After implementation, provide:
- Summary of changes made
- List of files modified/created
- Test results
- Any risks or concerns

## Rules
- Follow existing code conventions exactly
- Write tests for all new behavior
- Do not modify files outside the plan scope
- Run tests before declaring done
- Keep changes minimal and focused
```

**Step 5: Create QA prompt**

```markdown
# QA Agent

You are a QA agent. Your job is to validate the implementation.

## Input
You will receive:
- The specification with acceptance criteria
- The current state of the codebase

## Actions
- Run the project's lint command
- Run the project's test command
- Run type checking if configured

## Output
Provide structured results:

### Lint Results
- Command run
- Exit code
- Output (stdout/stderr)

### Test Results
- Command run
- Exit code
- Tests passed/failed/skipped
- Output (stdout/stderr)

### Type Check Results
- Command run
- Exit code
- Output

## Rules
- Report results exactly as they are — do not fix issues
- Capture full stdout and stderr
- Report exit codes
```

**Step 6: Create Reviewer prompt**

```markdown
# Reviewer Agent

You are a Code Reviewer agent. Your job is to evaluate the implementation quality.

## Input
You will receive:
- The specification
- The architecture notes
- QA results (lint/test output)
- The code diff

## Output
Produce a review report:

### Correctness
Does the implementation satisfy the acceptance criteria?

### Edge Cases
Are edge cases from the spec handled?

### Security
Any security risks (injection, auth, data exposure)?

### Performance
Any performance concerns?

### Required Changes
Numbered list of changes that MUST be made before approval. Empty if none.

## Rules
- Be specific: reference file names and line numbers
- Distinguish MUST-FIX from suggestions
- Do not rewrite code — describe what needs to change
```

**Step 7: Create Gatekeeper prompt**

```markdown
# Gatekeeper Agent

You are a Gatekeeper agent. Your job is to make a PASS/FAIL decision on the implementation.

## Input
You will receive:
- The specification
- The architecture notes
- QA results
- The reviewer report

## Scoring Rubric
Score each category 0-3:
1. **Acceptance criteria met** (0-3)
2. **Tests pass** (0-3)
3. **Lint passes** (0-3)
4. **No required changes from reviewer** (0-3)
5. **No security issues** (0-3)

Total: 0-15. PASS threshold: 12.

## Output
You MUST output ONLY valid JSON:

```json
{
  "scores": {
    "acceptance_criteria": 0,
    "tests": 0,
    "lint": 0,
    "review_clean": 0,
    "security": 0
  },
  "total_score": 0,
  "decision": "PASS or FAIL",
  "reasons": ["..."],
  "required_fixes": ["..."]
}
```

## Rules
- Output ONLY JSON, no other text
- Be strict — if tests fail, score 0 for tests
- FAIL if any required_fixes exist
- PASS requires score >= 12
```

**Step 8: Commit**

```bash
git add backend/app/prompts/
git commit -m "feat: add agent prompt templates for all 7 pipeline agents"
```

---

## Task 6: LangGraph Orchestrator

**Files:**
- Create: `backend/app/engine/orchestrator.py`
- Create: `backend/tests/test_orchestrator.py`

**Step 1: Write test for pipeline state and graph structure**

Create `backend/tests/test_orchestrator.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL

**Step 3: Implement orchestrator.py**

```python
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
        gate_result = {"decision": "FAIL", "reasons": ["Failed to parse gatekeeper output"]}

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
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_orchestrator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/engine/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: add LangGraph orchestrator with sequential pipeline and conditional gate"
```

---

## Task 7: API Endpoints — Pipeline Runs

**Files:**
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/runs.py`
- Create: `backend/app/routers/stream.py`
- Create: `backend/tests/test_runs_api.py`
- Modify: `backend/app/main.py`

**Step 1: Write test for runs API**

Create `backend/tests/test_runs_api.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_create_run():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/runs",
            json={
                "repo_url": "https://github.com/user/repo",
                "base_branch": "main",
                "feature_name": "add login",
                "requirements": "Add a login page with email/password",
            },
        )
    assert response.status_code == 201
    data = response.json()
    assert data["feature_name"] == "add login"
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_runs():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/runs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_run_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/runs/nonexistent")
    assert response.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_runs_api.py -v`
Expected: FAIL

**Step 3: Implement runs router**

Create `backend/app/routers/__init__.py` (empty).

Create `backend/app/routers/runs.py`:

```python
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
```

**Step 4: Implement SSE stream endpoint**

Create `backend/app/routers/stream.py`:

```python
import asyncio
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/stream", tags=["stream"])

# In-memory event bus (simple dict of run_id -> asyncio.Queue)
_event_queues: dict[str, list[asyncio.Queue]] = {}


def publish_event(run_id: str, event_type: str, data: dict):
    """Publish an event to all listeners for a run."""
    if run_id in _event_queues:
        for queue in _event_queues[run_id]:
            queue.put_nowait({"event": event_type, "data": json.dumps(data)})


@router.get("/{run_id}")
async def stream_run(run_id: str):
    queue: asyncio.Queue = asyncio.Queue()
    _event_queues.setdefault(run_id, []).append(queue)

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield event
                if event.get("event") == "pipeline_complete":
                    break
        finally:
            _event_queues[run_id].remove(queue)
            if not _event_queues[run_id]:
                del _event_queues[run_id]

    return EventSourceResponse(event_generator())
```

**Step 5: Register routers in main.py**

Update `backend/app/main.py` — add after middleware:

```python
from app.routers import runs, stream

app.include_router(runs.router)
app.include_router(stream.router)
```

**Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_runs_api.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add backend/app/routers/ backend/tests/test_runs_api.py backend/app/main.py
git commit -m "feat: add pipeline runs API with CRUD endpoints and SSE streaming"
```

---

## Task 8: GitHub Integration

**Files:**
- Create: `backend/app/engine/github.py`
- Create: `backend/tests/test_github.py`

**Step 1: Write test**

Create `backend/tests/test_github.py`:

```python
from app.engine.github import build_pr_body


def test_build_pr_body():
    body = build_pr_body(
        feature_name="add login",
        spec="Login spec...",
        architecture="Architecture notes...",
        gate_result={"total_score": 14, "decision": "PASS"},
    )
    assert "add login" in body
    assert "PASS" in body
    assert "Login spec" in body
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_github.py -v`
Expected: FAIL

**Step 3: Implement github.py**

```python
import subprocess
from pathlib import Path


def push_branch(sandbox_path: str, branch_name: str) -> None:
    """Push the sandbox branch to origin."""
    subprocess.run(
        ["git", "push", "origin", branch_name],
        cwd=sandbox_path,
        check=True,
        capture_output=True,
    )


def create_pull_request(
    sandbox_path: str,
    branch_name: str,
    base_branch: str,
    title: str,
    body: str,
) -> str:
    """Create a PR using gh CLI. Returns the PR URL."""
    result = subprocess.run(
        [
            "gh", "pr", "create",
            "--title", title,
            "--body", body,
            "--base", base_branch,
            "--head", branch_name,
        ],
        cwd=sandbox_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def build_pr_body(
    feature_name: str,
    spec: str,
    architecture: str,
    gate_result: dict,
) -> str:
    """Build the PR description body."""
    score = gate_result.get("total_score", "N/A")
    decision = gate_result.get("decision", "N/A")

    return f"""## {feature_name}

**Gate Score:** {score}/15
**Decision:** {decision}

---

### Specification
{spec}

### Architecture
{architecture}

---
*Generated by SoloCarta AI Pipeline*
"""
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_github.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/engine/github.py backend/tests/test_github.py
git commit -m "feat: add GitHub integration for branch push and PR creation"
```

---

## Task 9: Pipeline Execution Trigger

**Files:**
- Create: `backend/app/engine/runner.py`
- Modify: `backend/app/routers/runs.py`

**Step 1: Implement runner.py**

This ties the LangGraph pipeline to the API — starts a run as a background task.

```python
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
```

**Step 2: Add trigger endpoint to runs router**

Add to `backend/app/routers/runs.py`:

```python
import asyncio
from app.engine.runner import execute_pipeline


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
```

**Step 3: Commit**

```bash
git add backend/app/engine/runner.py backend/app/routers/runs.py
git commit -m "feat: add pipeline execution runner with background task trigger"
```

---

## Task 10: Frontend Scaffolding

**Files:**
- Create: `frontend/` (Vite + React + TypeScript + Tailwind)

**Step 1: Scaffold Vite project**

```bash
cd /Users/parker/Desktop/Dev/SoloCarta
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite
npm install react-router-dom
```

**Step 2: Configure Tailwind**

Update `frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

Update `frontend/src/index.css`:

```css
@import "tailwindcss";
```

**Step 3: Create basic App with routing**

Update `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import NewRun from './pages/NewRun'
import RunDetail from './pages/RunDetail'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <nav className="border-b border-gray-800 px-6 py-4">
          <div className="flex items-center gap-6">
            <Link to="/" className="text-xl font-bold text-white">
              SoloCarta
            </Link>
            <Link to="/new" className="text-sm text-gray-400 hover:text-white">
              New Run
            </Link>
          </div>
        </nav>
        <main className="mx-auto max-w-6xl px-6 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/new" element={<NewRun />} />
            <Route path="/run/:id" element={<RunDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
```

**Step 4: Verify it runs**

```bash
cd frontend && npm run dev
```

Open http://localhost:5173 — should see SoloCarta nav.

**Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold React frontend with Vite, Tailwind, and routing"
```

---

## Task 11: Dashboard Page

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`

**Step 1: Implement Dashboard**

```tsx
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

interface Run {
  id: string
  feature_name: string
  status: string
  current_step: string | null
  gate_score: number | null
  gate_decision: string | null
  created_at: string
}

export default function Dashboard() {
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/runs')
      .then((r) => r.json())
      .then(setRuns)
      .finally(() => setLoading(false))
  }, [])

  const statusColor = (status: string) => {
    switch (status) {
      case 'passed': return 'text-green-400'
      case 'failed': return 'text-red-400'
      case 'running': return 'text-yellow-400'
      case 'error': return 'text-red-500'
      default: return 'text-gray-400'
    }
  }

  if (loading) return <p className="text-gray-500">Loading...</p>

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold">Pipeline Runs</h1>
      {runs.length === 0 ? (
        <p className="text-gray-500">
          No runs yet.{' '}
          <Link to="/new" className="text-blue-400 hover:underline">
            Create one
          </Link>
        </p>
      ) : (
        <div className="space-y-3">
          {runs.map((run) => (
            <Link
              key={run.id}
              to={`/run/${run.id}`}
              className="block rounded-lg border border-gray-800 p-4 hover:border-gray-700"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold">{run.feature_name}</h2>
                  <p className="text-sm text-gray-500">
                    {run.current_step ?? 'pending'}
                  </p>
                </div>
                <span className={`text-sm font-medium ${statusColor(run.status)}`}>
                  {run.status}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: add Dashboard page with pipeline run list"
```

---

## Task 12: New Run Page

**Files:**
- Create: `frontend/src/pages/NewRun.tsx`

**Step 1: Implement NewRun form**

```tsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function NewRun() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    repo_url: '',
    base_branch: 'main',
    feature_name: '',
    requirements: '',
  })
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)

    const res = await fetch('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    const run = await res.json()

    // Start the pipeline
    await fetch(`/api/runs/${run.id}/start`, { method: 'POST' })

    navigate(`/run/${run.id}`)
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-6 text-2xl font-bold">New Pipeline Run</h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1 block text-sm text-gray-400">Repository URL</label>
          <input
            type="text"
            value={form.repo_url}
            onChange={(e) => setForm({ ...form, repo_url: e.target.value })}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            placeholder="https://github.com/user/repo or /path/to/local/repo"
            required
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-gray-400">Base Branch</label>
          <input
            type="text"
            value={form.base_branch}
            onChange={(e) => setForm({ ...form, base_branch: e.target.value })}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-gray-400">Feature Name</label>
          <input
            type="text"
            value={form.feature_name}
            onChange={(e) => setForm({ ...form, feature_name: e.target.value })}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            placeholder="add user authentication"
            required
          />
        </div>
        <div>
          <label className="mb-1 block text-sm text-gray-400">Requirements</label>
          <textarea
            value={form.requirements}
            onChange={(e) => setForm({ ...form, requirements: e.target.value })}
            className="w-full rounded border border-gray-700 bg-gray-900 px-3 py-2 text-white"
            rows={6}
            placeholder="Describe what you want built..."
            required
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-500 disabled:opacity-50"
        >
          {submitting ? 'Starting...' : 'Start Pipeline'}
        </button>
      </form>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/NewRun.tsx
git commit -m "feat: add NewRun page with pipeline creation form"
```

---

## Task 13: Run Detail Page with SSE

**Files:**
- Create: `frontend/src/hooks/useSSE.ts`
- Create: `frontend/src/pages/RunDetail.tsx`
- Create: `frontend/src/components/PipelineTimeline.tsx`
- Create: `frontend/src/components/AgentCard.tsx`

**Step 1: Implement SSE hook**

Create `frontend/src/hooks/useSSE.ts`:

```typescript
import { useEffect, useRef, useState } from 'react'

interface SSEEvent {
  event: string
  data: any
}

export function useSSE(url: string) {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [connected, setConnected] = useState(false)
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    const source = new EventSource(url)
    sourceRef.current = source

    source.onopen = () => setConnected(true)

    source.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        setEvents((prev) => [...prev, { event: 'message', data }])
      } catch {
        // ignore parse errors
      }
    }

    source.addEventListener('status', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      setEvents((prev) => [...prev, { event: 'status', data }])
    })

    source.addEventListener('pipeline_complete', (e: MessageEvent) => {
      const data = JSON.parse(e.data)
      setEvents((prev) => [...prev, { event: 'pipeline_complete', data }])
      source.close()
    })

    source.onerror = () => {
      setConnected(false)
      source.close()
    }

    return () => source.close()
  }, [url])

  return { events, connected }
}
```

**Step 2: Implement PipelineTimeline**

Create `frontend/src/components/PipelineTimeline.tsx`:

```tsx
const STEPS = ['sandbox_setup', 'pm', 'architect', 'planner', 'dev', 'qa', 'reviewer', 'gatekeeper']

interface Props {
  currentStep: string | null
  status: string
}

export default function PipelineTimeline({ currentStep, status }: Props) {
  const currentIndex = currentStep ? STEPS.indexOf(currentStep) : -1

  return (
    <div className="flex gap-2">
      {STEPS.map((step, i) => {
        let color = 'bg-gray-800 text-gray-500'
        if (status === 'passed' || status === 'failed') {
          color = i <= currentIndex ? 'bg-gray-700 text-gray-300' : 'bg-gray-800 text-gray-500'
        } else if (i < currentIndex) {
          color = 'bg-green-900 text-green-300'
        } else if (i === currentIndex) {
          color = 'bg-yellow-900 text-yellow-300'
        }

        return (
          <div key={step} className={`rounded px-3 py-1 text-xs font-medium ${color}`}>
            {step}
          </div>
        )
      })}
    </div>
  )
}
```

**Step 3: Implement AgentCard**

Create `frontend/src/components/AgentCard.tsx`:

```tsx
interface Props {
  name: string
  output: string | null
  status: 'pending' | 'running' | 'completed'
}

export default function AgentCard({ name, output, status }: Props) {
  return (
    <div className="rounded-lg border border-gray-800 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-semibold capitalize">{name} Agent</h3>
        <span className={`text-xs ${
          status === 'completed' ? 'text-green-400' :
          status === 'running' ? 'text-yellow-400' :
          'text-gray-500'
        }`}>
          {status}
        </span>
      </div>
      {output && (
        <pre className="max-h-64 overflow-auto rounded bg-gray-900 p-3 text-xs text-gray-300">
          {output}
        </pre>
      )}
    </div>
  )
}
```

**Step 4: Implement RunDetail page**

Create `frontend/src/pages/RunDetail.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useSSE } from '../hooks/useSSE'
import PipelineTimeline from '../components/PipelineTimeline'

interface Run {
  id: string
  feature_name: string
  requirements: string
  status: string
  current_step: string | null
  gate_score: number | null
  gate_decision: string | null
  error: string | null
  pr_url: string | null
}

export default function RunDetail() {
  const { id } = useParams<{ id: string }>()
  const [run, setRun] = useState<Run | null>(null)
  const { events } = useSSE(`/api/stream/${id}`)

  useEffect(() => {
    fetch(`/api/runs/${id}`)
      .then((r) => r.json())
      .then(setRun)
  }, [id])

  // Refresh run data when SSE events arrive
  useEffect(() => {
    if (events.length > 0) {
      fetch(`/api/runs/${id}`)
        .then((r) => r.json())
        .then(setRun)
    }
  }, [events.length, id])

  if (!run) return <p className="text-gray-500">Loading...</p>

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold">{run.feature_name}</h1>
      <p className="mb-6 text-sm text-gray-500">{run.requirements}</p>

      <PipelineTimeline currentStep={run.current_step} status={run.status} />

      <div className="mt-6 rounded-lg border border-gray-800 p-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Status:</span>{' '}
            <span className="font-medium">{run.status}</span>
          </div>
          <div>
            <span className="text-gray-500">Current Step:</span>{' '}
            <span className="font-medium">{run.current_step ?? '—'}</span>
          </div>
          {run.gate_score !== null && (
            <div>
              <span className="text-gray-500">Gate Score:</span>{' '}
              <span className="font-medium">{run.gate_score}/15</span>
            </div>
          )}
          {run.gate_decision && (
            <div>
              <span className="text-gray-500">Decision:</span>{' '}
              <span className={`font-medium ${
                run.gate_decision === 'PASS' ? 'text-green-400' : 'text-red-400'
              }`}>
                {run.gate_decision}
              </span>
            </div>
          )}
          {run.pr_url && (
            <div className="col-span-2">
              <a href={run.pr_url} target="_blank" rel="noreferrer" className="text-blue-400 hover:underline">
                View Pull Request
              </a>
            </div>
          )}
          {run.error && (
            <div className="col-span-2">
              <pre className="rounded bg-red-950 p-3 text-xs text-red-300">{run.error}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
```

**Step 5: Commit**

```bash
git add frontend/src/hooks/ frontend/src/pages/RunDetail.tsx frontend/src/components/
git commit -m "feat: add RunDetail page with SSE streaming and pipeline timeline"
```

---

## Task 14: Integration Test — End to End

**Files:**
- Create: `backend/tests/test_integration.py`

**Step 1: Write integration test**

This test verifies the full API flow (create run, check status) without calling Claude (mock the agent runtime).

```python
import pytest
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_full_api_flow():
    """Test: create run → get run → verify state."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create
        res = await client.post("/api/runs", json={
            "repo_url": "/tmp/test-repo",
            "base_branch": "main",
            "feature_name": "test feature",
            "requirements": "Build a test feature",
        })
        assert res.status_code == 201
        run = res.json()
        run_id = run["id"]

        # Get
        res = await client.get(f"/api/runs/{run_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "pending"

        # List
        res = await client.get("/api/runs")
        assert res.status_code == 200
        assert len(res.json()) >= 1
```

**Step 2: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add backend/tests/test_integration.py
git commit -m "test: add integration test for full API flow"
```

---

## Task 15: Final Wiring + Verify

**Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All PASS

**Step 2: Start backend**

Run: `cd backend && uvicorn app.main:app --reload`
Verify: http://localhost:8000/health returns `{"status": "ok"}`
Verify: http://localhost:8000/docs shows Swagger UI

**Step 3: Start frontend**

Run: `cd frontend && npm run dev`
Verify: http://localhost:5173 shows SoloCarta dashboard

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final wiring and cleanup for MVP scaffold"
```

---

## Summary

| Task | What | Key Files |
|------|------|-----------|
| 1 | Backend scaffolding | `main.py`, `config.py`, `pyproject.toml` |
| 2 | Database models | `models.py`, `database.py` |
| 3 | Sandbox engine | `engine/sandbox.py` |
| 4 | Claude runtime wrapper | `engine/claude_runtime.py` |
| 5 | Agent prompts | `prompts/*.md` |
| 6 | LangGraph orchestrator | `engine/orchestrator.py` |
| 7 | API endpoints | `routers/runs.py`, `routers/stream.py` |
| 8 | GitHub integration | `engine/github.py` |
| 9 | Pipeline runner | `engine/runner.py` |
| 10 | Frontend scaffold | Vite + React + Tailwind |
| 11 | Dashboard page | `pages/Dashboard.tsx` |
| 12 | New Run page | `pages/NewRun.tsx` |
| 13 | Run Detail + SSE | `pages/RunDetail.tsx`, `hooks/useSSE.ts` |
| 14 | Integration tests | `tests/test_integration.py` |
| 15 | Final wiring | Verify everything runs |
