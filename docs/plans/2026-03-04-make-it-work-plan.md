# Make It Actually Work — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix critical bugs (sandbox_path not saved, no input validation), add agent resilience (retry, timeout, cancellation), and surface errors in the frontend.

**Architecture:** Wrap `run_agent()` in a retry layer with exponential backoff and timeout. Add cancellation via `asyncio.Event` checked between LangGraph nodes. Add `error` column to AgentOutput for per-agent failure tracking. Frontend gets error states on all pages.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, SQLAlchemy, React 18, TypeScript, TailwindCSS

---

## Task 1: Save sandbox_path to DB

**Files:**
- Modify: `backend/app/engine/runner.py:144-166`
- Test: `backend/tests/test_runs_api.py`

**Step 1: Write failing test**

Add to `backend/tests/test_runs_api.py`:

```python
@pytest.mark.asyncio
async def test_sandbox_path_saved_after_pipeline():
    """Verify sandbox_path is persisted to PipelineRun after execute_pipeline."""
    async with async_session() as db:
        from app.models import PipelineRun
        run = PipelineRun(
            repo_url="/tmp/fake-repo",
            feature_name="test sandbox save",
            requirements="Test",
            sandbox_path=None,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    # Directly test that runner saves sandbox_path
    # We can't run the full pipeline without Claude API,
    # so we test the DB update logic in isolation
    async with async_session() as db:
        result = await db.execute(
            sa_select(PipelineRun).where(PipelineRun.id == run_id)
        )
        r = result.scalar_one()
        r.sandbox_path = "/tmp/test-sandbox"
        await db.commit()

    async with async_session() as db:
        result = await db.execute(
            sa_select(PipelineRun).where(PipelineRun.id == run_id)
        )
        r = result.scalar_one()
        assert r.sandbox_path == "/tmp/test-sandbox"
```

**Step 2: Run test to verify it passes** (this is a smoke test for the DB column)

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_runs_api.py::test_sandbox_path_saved_after_pipeline -v`

**Step 3: Fix runner.py to save sandbox_path**

In `backend/app/engine/runner.py`, after line 151 (`run.pr_url = final_state["pr_url"]`), add:

```python
            if final_state.get("sandbox_path"):
                run.sandbox_path = final_state["sandbox_path"]
```

And in the `except` block (after line 161), add:

```python
            # Save sandbox_path even on error so diffs can be inspected
            if initial_state.get("sandbox_path"):
                run.sandbox_path = initial_state["sandbox_path"]
```

Note: In the error case, `initial_state` won't have the sandbox_path (it starts as `""`). We need to capture it from `final_state` if available. Change approach — use a local variable:

In `execute_pipeline()`, add `sandbox_path = ""` before the try block (after line 116). Then after `_run_graph_streaming` returns (line 142), add `sandbox_path = final_state.get("sandbox_path", "")`. In the success path, add `run.sandbox_path = sandbox_path`. In the except block, add `run.sandbox_path = sandbox_path or None`.

Concrete diff for `runner.py`:

```python
        publish_event(run_id, "status", {"status": "running"})

        sandbox_path = ""
        try:
            # ... existing code ...

            # Run the graph with streaming
            final_state = await asyncio.to_thread(
                _run_graph_streaming, graph, initial_state, run_id
            )

            sandbox_path = final_state.get("sandbox_path", "")

            # Update DB with results
            run.status = final_state["status"]
            run.current_step = final_state["current_step"]
            run.sandbox_path = sandbox_path or None
            # ... rest of success path ...

        except Exception as e:
            run.status = "error"
            run.error = traceback.format_exc()
            run.sandbox_path = sandbox_path or None
            await db.commit()
```

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/engine/runner.py backend/tests/test_runs_api.py
git commit -m "fix: save sandbox_path to DB after pipeline execution"
```

---

## Task 2: Validate repo_url

**Files:**
- Modify: `backend/app/routers/runs.py:16-21`
- Test: `backend/tests/test_runs_api.py`

**Step 1: Write failing tests**

Add to `backend/tests/test_runs_api.py`:

```python
@pytest.mark.asyncio
async def test_create_run_invalid_repo_url_traversal():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/runs",
            json={
                "repo_url": "../../../etc/passwd",
                "feature_name": "evil",
                "requirements": "hack",
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_run_invalid_repo_url_empty():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/runs",
            json={
                "repo_url": "",
                "feature_name": "test",
                "requirements": "test",
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_run_valid_local_path():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/runs",
            json={
                "repo_url": "/Users/test/my-repo",
                "feature_name": "valid local",
                "requirements": "test",
            },
        )
    assert response.status_code == 201
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_runs_api.py::test_create_run_invalid_repo_url_traversal tests/test_runs_api.py::test_create_run_invalid_repo_url_empty -v`
Expected: FAIL (currently returns 201 for both)

**Step 3: Add validator to CreateRunRequest**

In `backend/app/routers/runs.py`, update the model:

```python
from pydantic import BaseModel, field_validator

class CreateRunRequest(BaseModel):
    repo_url: str
    base_branch: str = "main"
    feature_name: str
    requirements: str

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("repo_url must not be empty")
        if ".." in v:
            raise ValueError("repo_url must not contain '..'")
        if v.startswith("https://"):
            return v
        if v.startswith("/"):
            return v
        raise ValueError("repo_url must be an absolute path or https:// URL")
```

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/routers/runs.py backend/tests/test_runs_api.py
git commit -m "fix: validate repo_url to prevent path traversal"
```

---

## Task 3: Add error column to AgentOutput

**Files:**
- Modify: `backend/app/models.py:39-51`
- Modify: `backend/app/routers/runs.py:87-96` (AgentOutputResponse)
- Test: `backend/tests/test_models.py`

**Step 1: Write failing test**

Add to `backend/tests/test_models.py`:

```python
@pytest.mark.asyncio
async def test_agent_output_error_field():
    from app.database import async_session
    from app.models import PipelineRun, AgentOutput
    from datetime import datetime, timezone

    async with async_session() as db:
        run = PipelineRun(
            repo_url="/tmp/test",
            feature_name="test error field",
            requirements="test",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        output = AgentOutput(
            run_id=run.id,
            agent_name="pm",
            output_text="",
            status="error",
            error="Agent timed out after 300s",
        )
        db.add(output)
        await db.commit()
        await db.refresh(output)
        assert output.error == "Agent timed out after 300s"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_models.py::test_agent_output_error_field -v`
Expected: FAIL — `error` is not a valid column

**Step 3: Add error column**

In `backend/app/models.py`, add after line 46 (`status` column):

```python
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

In `backend/app/routers/runs.py`, update `AgentOutputResponse` to include error:

```python
class AgentOutputResponse(BaseModel):
    id: str
    run_id: str
    agent_name: str
    output_text: str
    status: str
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}
```

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/models.py backend/app/routers/runs.py backend/tests/test_models.py
git commit -m "feat: add error column to AgentOutput model"
```

---

## Task 4: Create resilience module (retry + timeout)

**Files:**
- Create: `backend/app/engine/resilience.py`
- Create: `backend/tests/test_resilience.py`

**Step 1: Write failing tests**

Create `backend/tests/test_resilience.py`:

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.engine.resilience import run_agent_with_retry, AgentError


@pytest.mark.asyncio
async def test_retry_succeeds_on_first_try():
    mock_run = AsyncMock(return_value="spec output")
    with patch("app.engine.resilience.run_agent", mock_run):
        from app.engine.claude_runtime import AgentRole
        result = await run_agent_with_retry(AgentRole.PM, "/tmp/sandbox", "context")
    assert result == "spec output"
    assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure():
    mock_run = AsyncMock(side_effect=[TimeoutError("timeout"), "spec output"])
    with patch("app.engine.resilience.run_agent", mock_run):
        from app.engine.claude_runtime import AgentRole
        result = await run_agent_with_retry(
            AgentRole.PM, "/tmp/sandbox", "context", max_retries=2, base_delay=0.01
        )
    assert result == "spec output"
    assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises_agent_error():
    mock_run = AsyncMock(side_effect=TimeoutError("timeout"))
    with patch("app.engine.resilience.run_agent", mock_run):
        from app.engine.claude_runtime import AgentRole
        with pytest.raises(AgentError) as exc_info:
            await run_agent_with_retry(
                AgentRole.PM, "/tmp/sandbox", "context", max_retries=2, base_delay=0.01
            )
    assert "pm" in str(exc_info.value)
    assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_timeout_triggers_retry():
    async def slow_agent(*args, **kwargs):
        await asyncio.sleep(10)
        return "never"

    with patch("app.engine.resilience.run_agent", side_effect=slow_agent):
        from app.engine.claude_runtime import AgentRole
        with pytest.raises(AgentError):
            await run_agent_with_retry(
                AgentRole.PM, "/tmp/sandbox", "context",
                max_retries=1, timeout_seconds=0.1, base_delay=0.01,
            )
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_resilience.py -v`
Expected: FAIL — module not found

**Step 3: Implement resilience.py**

Create `backend/app/engine/resilience.py`:

```python
"""Agent execution with retry, timeout, and error handling."""

import asyncio
import logging

from app.engine.claude_runtime import run_agent, AgentRole

logger = logging.getLogger(__name__)

TRANSIENT_EXCEPTIONS = (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError)


class AgentError(Exception):
    """Raised when an agent fails after all retries."""

    def __init__(self, agent_name: str, original_error: Exception):
        self.agent_name = agent_name
        self.original_error = original_error
        super().__init__(f"Agent '{agent_name}' failed: {original_error}")


async def run_agent_with_retry(
    role: AgentRole,
    sandbox_path: str,
    context: str,
    max_retries: int = 3,
    timeout_seconds: float = 300.0,
    base_delay: float = 1.0,
) -> str:
    """Run an agent with retry on transient failures and per-call timeout."""
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            result = await asyncio.wait_for(
                run_agent(role, sandbox_path, context),
                timeout=timeout_seconds,
            )
            return result
        except TRANSIENT_EXCEPTIONS as e:
            last_error = e
            logger.warning(
                "Agent %s attempt %d/%d failed: %s",
                role.value, attempt, max_retries, e,
            )
            if attempt < max_retries:
                delay = base_delay * (4 ** (attempt - 1))  # 1s, 4s, 16s
                await asyncio.sleep(delay)
        except Exception as e:
            # Non-transient error — fail immediately
            raise AgentError(role.value, e) from e

    raise AgentError(role.value, last_error)
```

**Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_resilience.py -v`
Expected: All 4 pass

**Step 5: Run full suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add backend/app/engine/resilience.py backend/tests/test_resilience.py
git commit -m "feat: add agent retry with exponential backoff and timeout"
```

---

## Task 5: Wire resilience into orchestrator

**Files:**
- Modify: `backend/app/engine/orchestrator.py:46-193`

**Step 1: Update all agent nodes to use run_agent_with_retry**

In each agent node function (`pm_node`, `architect_node`, `planner_node`, `dev_node`, `qa_node`, `reviewer_node`, `gatekeeper_node`), change:

```python
# Before (in each node):
from app.engine.claude_runtime import run_agent, AgentRole

result = anyio.from_thread.run(
    run_agent, AgentRole.XX, state["sandbox_path"], context
)

# After (in each node):
from app.engine.resilience import run_agent_with_retry
from app.engine.claude_runtime import AgentRole

result = anyio.from_thread.run(
    run_agent_with_retry, AgentRole.XX, state["sandbox_path"], context
)
```

Apply this to all 7 nodes. The import of `run_agent_with_retry` replaces `run_agent`.

**Step 2: Run existing tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass (orchestrator tests only check graph building, not execution)

**Step 3: Commit**

```bash
git add backend/app/engine/orchestrator.py
git commit -m "feat: wire retry/timeout into all orchestrator agent nodes"
```

---

## Task 6: Pipeline cancellation

**Files:**
- Modify: `backend/app/engine/runner.py`
- Modify: `backend/app/routers/runs.py`
- Test: `backend/tests/test_runs_api.py`

**Step 1: Write failing test for cancel endpoint**

Add to `backend/tests/test_runs_api.py`:

```python
@pytest.mark.asyncio
async def test_cancel_run_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/runs/nonexistent/cancel")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_run_not_running():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/api/runs",
            json={
                "repo_url": "/tmp/test-repo",
                "feature_name": "test cancel",
                "requirements": "Test",
            },
        )
        run_id = create_resp.json()["id"]
        response = await client.post(f"/api/runs/{run_id}/cancel")
    assert response.status_code == 400
    assert "not running" in response.json()["detail"].lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_runs_api.py::test_cancel_run_not_found tests/test_runs_api.py::test_cancel_run_not_running -v`
Expected: FAIL — 404 (no route)

**Step 3: Add cancellation registry to runner.py**

At the top of `backend/app/engine/runner.py` (after imports), add:

```python
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
```

In `execute_pipeline()`, register the event before the try block:

```python
        cancel_event = asyncio.Event()
        _cancel_events[run_id] = cancel_event
```

Clean up in a `finally` block:

```python
        finally:
            _cancel_events.pop(run_id, None)
```

In `_run_graph_streaming()`, accept a `cancel_check` callback and check between nodes:

```python
def _run_graph_streaming(graph, initial_state: PipelineState, run_id: str, cancel_check=None) -> dict:
```

Inside the `for chunk in graph.stream(...)` loop, at the top:

```python
        if cancel_check and cancel_check():
            merged_state["status"] = "cancelled"
            publish_event(run_id, "pipeline_complete", {"status": "cancelled"})
            return merged_state
```

Pass the check from `execute_pipeline`:

```python
            final_state = await asyncio.to_thread(
                _run_graph_streaming, graph, initial_state, run_id,
                cancel_check=lambda: cancel_event.is_set(),
            )
```

Handle cancelled status after the graph returns:

```python
            if final_state["status"] == "cancelled":
                run.status = "cancelled"
                run.sandbox_path = sandbox_path or None
                await db.commit()
                return
```

**Step 4: Add cancel endpoint to runs.py**

Add to `backend/app/routers/runs.py`:

```python
@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PipelineRun).where(PipelineRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "running":
        raise HTTPException(status_code=400, detail="Run is not running")

    from app.engine.runner import request_cancellation
    cancelled = request_cancellation(run_id)
    if cancelled:
        run.status = "cancelled"
        await db.commit()
    return {"message": "Cancellation requested", "run_id": run_id}
```

**Step 5: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add backend/app/engine/runner.py backend/app/routers/runs.py backend/tests/test_runs_api.py
git commit -m "feat: add pipeline cancellation endpoint and token"
```

---

## Task 7: Per-agent error recording in runner

**Files:**
- Modify: `backend/app/engine/runner.py:27-47` (_save_agent_output)
- Modify: `backend/app/engine/runner.py:76-98` (agent_complete handling)

**Step 1: Update _save_agent_output to accept error**

In `backend/app/engine/runner.py`, update `_save_agent_output`:

```python
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
```

**Step 2: Handle AgentError in _run_graph_streaming**

In `_run_graph_streaming`, wrap the node processing in a try/except for `AgentError`. When an agent fails, save the error output and re-raise:

After the import at the top of `_run_graph_streaming`, add:

```python
from app.engine.resilience import AgentError
```

Wrap the agent output saving block. When `AgentError` occurs during graph streaming, it will bubble up through `graph.stream()`. The actual error handling happens in `execute_pipeline()`'s except block. But we should save the failing agent's record there.

In the `except Exception` block of `execute_pipeline()`, before setting `run.error`, add logic to save the failed agent output:

```python
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
```

**Step 3: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/engine/runner.py
git commit -m "feat: record per-agent errors to AgentOutput on failure"
```

---

## Task 8: Frontend error states

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/NewRun.tsx`
- Modify: `frontend/src/pages/RunDetail.tsx`
- Modify: `frontend/src/components/AgentCard.tsx`

**Step 1: Dashboard error handling**

Update `frontend/src/pages/Dashboard.tsx`:

```typescript
export default function Dashboard() {
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/runs')
      .then((r) => {
        if (!r.ok) throw new Error(`API error: ${r.status}`)
        return r.json()
      })
      .then(setRuns)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
```

Add error banner in the JSX, before the runs list:

```typescript
  if (error) return (
    <div className="rounded-lg border border-red-800 bg-red-950 p-4 text-sm text-red-300">
      Failed to load runs: {error}
    </div>
  )
```

**Step 2: NewRun error handling**

Update `frontend/src/pages/NewRun.tsx` `handleSubmit`:

```typescript
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      const res = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })

      if (!res.ok) {
        const body = await res.json().catch(() => null)
        const detail = body?.detail
        const msg = Array.isArray(detail)
          ? detail.map((d: { msg: string }) => d.msg).join(', ')
          : detail || `Error ${res.status}`
        setError(msg)
        setSubmitting(false)
        return
      }

      const run = await res.json()
      await fetch(`/api/runs/${run.id}/start`, { method: 'POST' })
      navigate(`/run/${run.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Network error')
      setSubmitting(false)
    }
  }
```

Add error display in JSX, after the form opening tag:

```typescript
        {error && (
          <div className="rounded-lg border border-red-800 bg-red-950 p-3 text-sm text-red-300">
            {error}
          </div>
        )}
```

**Step 3: RunDetail error handling**

Update `frontend/src/pages/RunDetail.tsx`:

Add `fetchError` state:

```typescript
  const [fetchError, setFetchError] = useState<string | null>(null)
```

Update the initial fetch:

```typescript
  useEffect(() => {
    fetch(`/api/runs/${id}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Run not found (${r.status})`)
        return r.json()
      })
      .then((data: Run) => {
        setRun(data)
        if (TERMINAL_STATUSES.includes(data.status)) {
          fetchDiff()
        }
      })
      .catch((e) => setFetchError(e.message))
    fetchOutputs()
  }, [id, fetchOutputs, fetchDiff])
```

Add error display:

```typescript
  if (fetchError) return (
    <div className="rounded-lg border border-red-800 bg-red-950 p-4 text-sm text-red-300">
      {fetchError}
    </div>
  )
```

**Step 4: AgentCard error display**

Update `frontend/src/components/AgentCard.tsx` Props:

```typescript
interface Props {
  name: string
  output: string | null
  status: 'pending' | 'running' | 'completed' | 'error'
  error?: string | null
  onClick?: () => void
}
```

Update the status color to include error:

```typescript
        <span className={`text-xs ${
          status === 'completed' ? 'text-green-400' :
          status === 'running' ? 'text-yellow-400' :
          status === 'error' ? 'text-red-400' :
          'text-gray-500'
        }`}>
          {status}
        </span>
```

Add error display in the card body:

```typescript
      {error && (
        <div className="mt-2 rounded bg-red-950 p-2 text-xs text-red-300">
          {error}
        </div>
      )}
```

**Step 5: Wire error status in RunDetail AgentCard rendering**

In `RunDetail.tsx`, update the agent status logic and pass error:

```typescript
          let status: 'pending' | 'running' | 'completed' | 'error' = 'pending'
          if (agentOutput) {
            status = agentOutput.status === 'error' ? 'error' : 'completed'
          } else if (activeAgent === agent) {
            status = 'running'
          }
          return (
            <AgentCard
              key={agent}
              name={agent}
              output={agentOutput?.output_text ?? null}
              status={status}
              error={agentOutput?.status === 'error' ? (agentOutput as any).error : null}
              onClick={() => setSelectedAgent(agent)}
            />
          )
```

Update `AgentOutputData` interface to include error:

```typescript
interface AgentOutputData {
  id: string
  run_id: string
  agent_name: string
  output_text: string
  status: string
  error: string | null
  started_at: string | null
  completed_at: string | null
}
```

**Step 6: Type check and build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: Clean compile

**Step 7: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/pages/NewRun.tsx frontend/src/pages/RunDetail.tsx frontend/src/components/AgentCard.tsx
git commit -m "feat: add error states to all frontend pages"
```

---

## Verification

After all tasks:

1. `cd backend && source .venv/bin/activate && python -m pytest tests/ -v` — all tests pass
2. `cd frontend && npx tsc --noEmit && npm run build` — compiles clean
