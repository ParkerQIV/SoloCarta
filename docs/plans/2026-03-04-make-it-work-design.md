# Make It Actually Work — Design

**Goal:** Fix critical bugs, add resilience, and surface errors properly so SoloCarta can run real pipelines reliably.

---

## 1. Critical Bug Fixes

### Save sandbox_path to DB
`runner.py` lines 144-151 update status, gate_score, gate_decision, and pr_url from final state — but never save `sandbox_path`. This means `GET /api/runs/{id}/diff` always returns 400 ("No sandbox for this run").

**Fix:** Add `run.sandbox_path = final_state["sandbox_path"]` after the graph completes. Also save it in the error handler if sandbox was created before the failure.

### Validate repo_url
`CreateRunRequest.repo_url` accepts any string. Malicious input like `../../../etc/passwd` could be passed to `create_sandbox()`.

**Fix:** Add Pydantic `field_validator` on `repo_url`:
- Must be non-empty
- Must be either an absolute path (`/`) or an `https://` URL
- No `..` path components allowed

---

## 2. Agent Retry + Timeout

### New module: `backend/app/engine/resilience.py`

`run_agent_with_retry(role, sandbox_path, context, max_retries=3, timeout_seconds=300)`:
- Wraps `claude_runtime.run_agent()` with `asyncio.wait_for()` for timeout
- On transient failure (timeout, connection error), retries with exponential backoff: 1s, 4s, 16s
- On final failure, raises `AgentError(agent_name, original_exception)`
- Non-transient errors (e.g., invalid API key) fail immediately

Each orchestrator node calls `run_agent_with_retry()` instead of `run_agent()`.

---

## 3. Pipeline Cancellation

### Cancellation token pattern
Module-level registry in `runner.py`: `_cancel_events: dict[str, asyncio.Event]`

- `execute_pipeline()` registers an event before starting the graph
- `_run_graph_streaming()` checks the event between each node via a callback
- If cancelled: sets `status="cancelled"`, emits SSE event, stops iteration
- Cleanup: event removed from registry when pipeline ends (success, error, or cancel)

### New endpoint: `POST /api/runs/{run_id}/cancel`
- Validates run exists and is currently "running"
- Sets the cancel event
- Updates DB: `status="cancelled"`
- Returns 200 with `{"message": "Cancellation requested"}`

---

## 4. Per-Agent Error Recording

### Schema change
Add `error` column to `AgentOutput` model: `Mapped[str | None] = mapped_column(Text, nullable=True)`

### Behavior
When an agent fails (after retries exhausted), `_run_graph_streaming()` saves an AgentOutput with:
- `status="error"`
- `output_text=""` (no output produced)
- `error=str(exception)`

The pipeline then re-raises so the global error handler catches it.

---

## 5. Frontend Error States

### Dashboard.tsx
- Add `error` state
- `.catch()` on fetch, set error message
- Render error banner above run list

### NewRun.tsx
- Check `res.ok` before parsing JSON
- On error: parse error detail from response body, display below form
- Disable submit button during request (already done), add error display

### RunDetail.tsx
- Add `error` state for fetch failures
- Show error message instead of infinite "Loading..."
- Show per-agent errors on AgentCards when `agentOutput.status === 'error'`

### AgentCard.tsx
- Accept optional `error` prop
- When status is 'error', show red border + error text

---

## Files Modified

| File | Change |
|------|--------|
| `backend/app/engine/runner.py` | Save sandbox_path, cancellation token, per-agent error recording |
| `backend/app/engine/resilience.py` | **Create** — retry wrapper with backoff + timeout |
| `backend/app/engine/orchestrator.py` | Switch to `run_agent_with_retry()` |
| `backend/app/routers/runs.py` | Add repo_url validation, cancel endpoint |
| `backend/app/models.py` | Add `error` column to AgentOutput |
| `backend/tests/test_runs_api.py` | Add cancel + validation tests |
| `backend/tests/test_resilience.py` | **Create** — retry/timeout tests |
| `frontend/src/pages/Dashboard.tsx` | Error state |
| `frontend/src/pages/NewRun.tsx` | Error handling on submit |
| `frontend/src/pages/RunDetail.tsx` | Error states, per-agent errors |
| `frontend/src/components/AgentCard.tsx` | Error display |

## Verification

1. `cd backend && python -m pytest tests/ -v` — all tests pass
2. `cd frontend && npx tsc --noEmit && npm run build` — compiles clean
