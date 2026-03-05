# Retry Logic Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When the gatekeeper returns FAIL, loop back through dev -> qa -> reviewer -> gatekeeper with feedback, up to a configurable number of retries.

**Architecture:** Add `retry_count`, `max_retries`, and `gate_feedback` fields to PipelineState. The gatekeeper node increments retry_count and sets gate_feedback. `route_gate_result` becomes a 3-way router: PASS -> create_pr, FAIL+retries -> dev, FAIL+exhausted -> fail. Dev node prepends gate feedback on retries.

**Tech Stack:** Python, LangGraph (StateGraph conditional edges), FastAPI, Pydantic, React/TypeScript

---

### Task 1: Add retry fields to PipelineState

**Files:**
- Modify: `backend/app/engine/orchestrator.py:23-44`
- Test: `backend/tests/test_orchestrator.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_orchestrator.py`:

```python
def test_pipeline_state_has_retry_fields():
    state = PipelineState(
        run_id="test-1",
        repo_url="https://github.com/user/repo",
        base_branch="main",
        sandbox_path="/tmp/sandbox",
        feature_name="test feature",
        requirements="do something",
        current_step="pending",
        status="pending",
        retry_count=0,
        max_retries=2,
    )
    assert state["retry_count"] == 0
    assert state["max_retries"] == 2
    assert state.get("gate_feedback") is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_orchestrator.py::test_pipeline_state_has_retry_fields -v`
Expected: FAIL — `retry_count` is not a valid key

**Step 3: Add retry fields to PipelineState**

In `backend/app/engine/orchestrator.py`, add to the `PipelineState` TypedDict after the `pr_url` field:

```python
    # Retry
    retry_count: int
    max_retries: int
    gate_feedback: str | None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_orchestrator.py::test_pipeline_state_has_retry_fields -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/engine/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: add retry_count, max_retries, gate_feedback to PipelineState"
```

---

### Task 2: Update gatekeeper_node to set gate_feedback and increment retry_count

**Files:**
- Modify: `backend/app/engine/orchestrator.py:178-202` (gatekeeper_node)
- Test: `backend/tests/test_orchestrator.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_orchestrator.py`:

```python
from unittest.mock import patch, AsyncMock

def test_gatekeeper_node_sets_feedback_on_fail():
    """gatekeeper_node should set gate_feedback and increment retry_count on FAIL."""
    from app.engine.orchestrator import gatekeeper_node

    state = PipelineState(
        run_id="t", repo_url="r", base_branch="main", sandbox_path="/tmp",
        feature_name="f", requirements="r", current_step="gatekeeper",
        status="running", spec="s", architecture="a", plan="p",
        implementation_summary="i", qa_results={"raw_output": "ok"},
        review_report="good", gate_result=None, error=None, pr_url=None,
        retry_count=0, max_retries=2, gate_feedback=None,
    )

    with patch("app.engine.orchestrator.anyio.from_thread.run") as mock_run:
        mock_run.return_value = '{"decision": "FAIL", "reasons": ["tests failing"]}'
        result = gatekeeper_node(state)

    assert result["gate_result"]["decision"] == "FAIL"
    assert result["retry_count"] == 1
    assert "tests failing" in result["gate_feedback"]


def test_gatekeeper_node_no_increment_on_pass():
    """gatekeeper_node should not increment retry_count on PASS."""
    from app.engine.orchestrator import gatekeeper_node

    state = PipelineState(
        run_id="t", repo_url="r", base_branch="main", sandbox_path="/tmp",
        feature_name="f", requirements="r", current_step="gatekeeper",
        status="running", spec="s", architecture="a", plan="p",
        implementation_summary="i", qa_results={"raw_output": "ok"},
        review_report="good", gate_result=None, error=None, pr_url=None,
        retry_count=0, max_retries=2, gate_feedback=None,
    )

    with patch("app.engine.orchestrator.anyio.from_thread.run") as mock_run:
        mock_run.return_value = '{"decision": "PASS", "score": 9}'
        result = gatekeeper_node(state)

    assert result["gate_result"]["decision"] == "PASS"
    assert "retry_count" not in result  # no change on PASS
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_orchestrator.py::test_gatekeeper_node_sets_feedback_on_fail tests/test_orchestrator.py::test_gatekeeper_node_no_increment_on_pass -v`
Expected: FAIL — gatekeeper_node doesn't return retry_count or gate_feedback

**Step 3: Update gatekeeper_node**

Replace the return in `gatekeeper_node` (orchestrator.py around line 200-202):

```python
    gate_result = parse_gate_json(result_text)

    result = {"gate_result": gate_result, "current_step": "done"}

    if gate_result.get("decision") != "PASS":
        reasons = gate_result.get("reasons", [])
        result["gate_feedback"] = "; ".join(reasons) if reasons else "Gate returned FAIL"
        result["retry_count"] = state.get("retry_count", 0) + 1

    return result
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_orchestrator.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/engine/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: gatekeeper sets gate_feedback and increments retry_count on FAIL"
```

---

### Task 3: Update route_gate_result to 3-way routing

**Files:**
- Modify: `backend/app/engine/orchestrator.py:205-210` (route_gate_result)
- Modify: `backend/app/engine/orchestrator.py:270-275` (build_pipeline_graph conditional edges)
- Test: `backend/tests/test_orchestrator.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_orchestrator.py`:

```python
from app.engine.orchestrator import route_gate_result

def test_route_gate_result_pass():
    state = {"gate_result": {"decision": "PASS"}, "retry_count": 0, "max_retries": 2}
    assert route_gate_result(state) == "create_pr"

def test_route_gate_result_fail_with_retries():
    state = {"gate_result": {"decision": "FAIL"}, "retry_count": 1, "max_retries": 2}
    assert route_gate_result(state) == "retry"

def test_route_gate_result_fail_exhausted():
    state = {"gate_result": {"decision": "FAIL"}, "retry_count": 2, "max_retries": 2}
    assert route_gate_result(state) == "fail"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_orchestrator.py::test_route_gate_result_fail_with_retries tests/test_orchestrator.py::test_route_gate_result_fail_exhausted -v`
Expected: FAIL — route returns "fail" instead of "retry"

**Step 3: Update route_gate_result and graph edges**

In `backend/app/engine/orchestrator.py`, replace `route_gate_result`:

```python
def route_gate_result(state: PipelineState) -> Literal["create_pr", "retry", "fail"]:
    """Route based on gatekeeper decision and retry count."""
    gate = state.get("gate_result", {})
    if gate.get("decision") == "PASS":
        return "create_pr"
    if state.get("retry_count", 0) < state.get("max_retries", 0):
        return "retry"
    return "fail"
```

In `build_pipeline_graph`, add a "retry" edge after the conditional edges block:

```python
    # Conditional edge after gatekeeper
    builder.add_conditional_edges("gatekeeper", route_gate_result)

    # Retry loops back to dev
    builder.add_edge("retry", "dev")  # NOT needed — "retry" maps to "dev" via routing
```

Wait — LangGraph conditional edges map return values to node names. So "retry" needs to map to "dev". Two options:
- Return "dev" directly from route_gate_result
- Use the path_map parameter

Simplest: return "dev" directly. Update the function:

```python
def route_gate_result(state: PipelineState) -> Literal["create_pr", "dev", "fail"]:
    """Route based on gatekeeper decision and retry count."""
    gate = state.get("gate_result", {})
    if gate.get("decision") == "PASS":
        return "create_pr"
    if state.get("retry_count", 0) < state.get("max_retries", 0):
        return "dev"
    return "fail"
```

Update tests to expect "dev" instead of "retry":

```python
def test_route_gate_result_fail_with_retries():
    state = {"gate_result": {"decision": "FAIL"}, "retry_count": 1, "max_retries": 2}
    assert route_gate_result(state) == "dev"
```

No graph changes needed — `dev` node already exists.

**Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_orchestrator.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/engine/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: 3-way gate routing — PASS/retry/fail based on retry_count"
```

---

### Task 4: Update dev_node to include gate feedback on retries

**Files:**
- Modify: `backend/app/engine/orchestrator.py:115-134` (dev_node)
- Test: `backend/tests/test_orchestrator.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_orchestrator.py`:

```python
def test_dev_node_includes_feedback_on_retry():
    """dev_node should include gate_feedback in context when retry_count > 0."""
    from app.engine.orchestrator import dev_node

    state = PipelineState(
        run_id="t", repo_url="r", base_branch="main", sandbox_path="/tmp",
        feature_name="f", requirements="r", current_step="dev",
        status="running", spec="s", architecture="a", plan="p",
        implementation_summary="i", qa_results=None,
        review_report="needs fixes", gate_result=None, error=None, pr_url=None,
        retry_count=1, max_retries=2, gate_feedback="tests failing; missing error handling",
    )

    with patch("app.engine.orchestrator.anyio.from_thread.run") as mock_run:
        mock_run.return_value = "fixed it"
        dev_node(state)

    call_args = mock_run.call_args
    context_arg = call_args[0][2]  # 3rd positional arg is context
    assert "Previous attempt failed" in context_arg
    assert "tests failing; missing error handling" in context_arg
    assert "needs fixes" in context_arg
```

**Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_orchestrator.py::test_dev_node_includes_feedback_on_retry -v`
Expected: FAIL — context doesn't include feedback

**Step 3: Update dev_node**

In `backend/app/engine/orchestrator.py`, replace dev_node:

```python
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

    if state.get("retry_count", 0) > 0 and state.get("gate_feedback"):
        context += f"""

--- RETRY ---
Previous attempt failed. Gatekeeper feedback:
{state['gate_feedback']}

Reviewer report:
{state.get('review_report', 'N/A')}

Fix the issues and try again."""

    summary = anyio.from_thread.run(
        run_agent, AgentRole.DEV, state["sandbox_path"], context
    )
    return {"implementation_summary": summary, "current_step": "qa"}
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_orchestrator.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/engine/orchestrator.py backend/tests/test_orchestrator.py
git commit -m "feat: dev_node includes gate feedback and reviewer report on retry"
```

---

### Task 5: Add max_retries to API and DB model

**Files:**
- Modify: `backend/app/models.py:18-36` (PipelineRun)
- Modify: `backend/app/routers/runs.py:18-52` (CreateRunRequest, RunResponse, create_run)
- Modify: `backend/app/engine/runner.py:119-137` (initial_state in execute_pipeline)
- Test: `backend/tests/test_runs_api.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_runs_api.py`:

```python
@pytest.mark.asyncio
async def test_create_run_with_max_retries(client):
    resp = client.post("/api/runs", json={
        "repo_url": "/tmp/repo",
        "feature_name": "retry test",
        "requirements": "test retries",
        "max_retries": 3,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["max_retries"] == 3


@pytest.mark.asyncio
async def test_create_run_default_max_retries(client):
    resp = client.post("/api/runs", json={
        "repo_url": "/tmp/repo",
        "feature_name": "default retry",
        "requirements": "test defaults",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["max_retries"] == 2
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_runs_api.py::test_create_run_with_max_retries tests/test_runs_api.py::test_create_run_default_max_retries -v`
Expected: FAIL — max_retries not in request/response

**Step 3: Add max_retries to model, request, response, and initial_state**

In `backend/app/models.py`, add to PipelineRun after `gate_decision`:

```python
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
```

In `backend/app/routers/runs.py`, update CreateRunRequest:

```python
class CreateRunRequest(BaseModel):
    repo_url: str
    base_branch: str = "main"
    feature_name: str
    requirements: str
    max_retries: int = 2
```

Update RunResponse to include `max_retries`:

```python
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
    max_retries: int

    model_config = {"from_attributes": True}
```

Update `create_run` to pass max_retries:

```python
    run = PipelineRun(
        repo_url=req.repo_url,
        base_branch=req.base_branch,
        feature_name=req.feature_name,
        requirements=req.requirements,
        max_retries=req.max_retries,
    )
```

In `backend/app/engine/runner.py`, update initial_state in `execute_pipeline` to include retry fields:

```python
            initial_state: PipelineState = {
                ...
                "retry_count": 0,
                "max_retries": run.max_retries,
                "gate_feedback": None,
            }
```

**Step 4: Run all tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/models.py backend/app/routers/runs.py backend/app/engine/runner.py backend/tests/test_runs_api.py
git commit -m "feat: add max_retries to API request, DB model, and pipeline initial state"
```

---

### Task 6: Emit retry SSE event from runner

**Files:**
- Modify: `backend/app/engine/runner.py:50-100` (_run_graph_streaming)

**Step 1: Update _run_graph_streaming to detect retries**

In `backend/app/engine/runner.py`, the streaming loop already tracks `node_started_at`. On retry, dev will execute again. We need to detect when dev runs a second time and emit a retry event.

Update `_run_graph_streaming` — after the `merged_state.update(update)` line, add retry detection:

```python
        # Detect retry: dev node running again means a retry loop
        if node_name == "dev" and "dev" in node_started_at:
            retry_count = merged_state.get("retry_count", 0)
            max_retries = merged_state.get("max_retries", 0)
            publish_event(run_id, "retry", {
                "retry_count": retry_count,
                "max_retries": max_retries,
            })
```

Also, allow `node_started_at` to be overwritten on retry (remove the `not in` guard for agent_start tracking), or reset it for retry nodes. Simplest: change the guard to always update `node_started_at`:

Replace:
```python
        if next_step and next_step in AGENT_NODES and next_step not in node_started_at:
```
With:
```python
        if next_step and next_step in AGENT_NODES:
```

This allows re-emitting agent_start on retries.

**Step 2: Run all tests**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add backend/app/engine/runner.py
git commit -m "feat: emit retry SSE event and re-emit agent_start on retry loops"
```

---

### Task 7: Add retry event listener to frontend

**Files:**
- Modify: `frontend/src/hooks/useSSE.ts`
- Modify: `frontend/src/pages/RunDetail.tsx`

**Step 1: Add retry event listener to useSSE.ts**

Add after the `agent_complete` listener (around line 41):

```typescript
    source.addEventListener('retry', (e) => {
      const data: unknown = JSON.parse((e as MessageEvent).data as string)
      setEvents((prev) => [...prev, { event: 'retry', data }])
    })
```

**Step 2: Show retry indicator in RunDetail.tsx**

Find where pipeline status is displayed and add retry detection. Extract retry info from events:

```typescript
const retryEvent = events.filter(e => e.event === 'retry').pop()
const retryInfo = retryEvent?.data as { retry_count: number; max_retries: number } | undefined
```

Display near the status area:

```tsx
{retryInfo && (
  <div className="text-amber-400 text-sm font-medium">
    Retry {retryInfo.retry_count}/{retryInfo.max_retries}
  </div>
)}
```

**Step 3: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/hooks/useSSE.ts frontend/src/pages/RunDetail.tsx
git commit -m "feat: display retry indicator in run detail UI"
```

---

### Task 8: Run full test suite and verify

**Step 1: Run all backend tests**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v`
Expected: All PASS

**Step 2: Run frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Final commit if any cleanup needed**

If all clean, push:
```bash
git push
```
