# Dogfood Loop — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Merge reliability fixes, add outcome tracking, add dashboard stats, and run SoloCarta on itself for the first time.

**Architecture:** Add `OutcomeLog` model linked to PipelineRun. Runner auto-creates outcome records after pipeline completion. New API endpoint returns structured outcome data. Dashboard gets a stats summary computed from run data.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, React 18, TypeScript, TailwindCSS

---

## Task 1: Merge PR #1 (make-it-work)

**Step 1: Merge the PR locally**

```bash
git fetch origin
git merge origin/feature/make-it-work
```

**Step 2: Verify tests pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/ -v`
Expected: All pass (25 tests)

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: Clean compile

**Step 3: Delete remote feature branch**

```bash
git push origin --delete feature/make-it-work
git branch -d feature/make-it-work
```

---

## Task 2: Add OutcomeLog model

**Files:**
- Modify: `backend/app/models.py` (after AgentOutput class)
- Test: `backend/tests/test_models.py`

**Step 1: Write failing test**

Add to `backend/tests/test_models.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_models.py::test_create_outcome_log -v`
Expected: FAIL — `OutcomeLog` not found

**Step 3: Add OutcomeLog model**

In `backend/app/models.py`, add after the AgentOutput class (after the `run` relationship line):

```python
from sqlalchemy import JSON, Float


class OutcomeLog(Base):
    __tablename__ = "outcome_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("pipeline_runs.id"), unique=True, nullable=False)
    total_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    agent_durations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gate_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    failure_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    run: Mapped["PipelineRun"] = relationship()
```

Note: The `JSON` and `Float` imports must be added to the existing import line at top of file:

```python
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, JSON, Float
```

**Step 4: Run test**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: All pass

**Step 5: Run full suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat: add OutcomeLog model for structured run tracking"
```

---

## Task 3: Wire outcome logging into runner

**Files:**
- Modify: `backend/app/engine/runner.py` (execute_pipeline function)
- Test: `backend/tests/test_models.py` (OutcomeLog already tested above)

**Step 1: Add _save_outcome helper**

In `backend/app/engine/runner.py`, add a new function after `_save_agent_output`:

```python
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
```

**Step 2: Call _save_outcome in execute_pipeline**

In `execute_pipeline()`, add a `pipeline_start` timestamp right after `publish_event(run_id, "status", {"status": "running"})`:

```python
        pipeline_start = datetime.now(timezone.utc)
```

In the **success path**, after `await db.commit()` and before `publish_event(run_id, "pipeline_complete", ...)`, add:

```python
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
```

In the **except block**, after `await db.commit()` and before `publish_event(...)`, add:

```python
            # Save outcome log for errors
            duration = (datetime.now(timezone.utc) - pipeline_start).total_seconds()
            fail_agent = None
            fail_category = "crash"
            from app.engine.resilience import AgentError
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
```

**Step 3: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add backend/app/engine/runner.py
git commit -m "feat: auto-create OutcomeLog after pipeline completion"
```

---

## Task 4: Add outcome API endpoint

**Files:**
- Modify: `backend/app/routers/runs.py`
- Test: `backend/tests/test_runs_api.py`

**Step 1: Write failing test**

Add to `backend/tests/test_runs_api.py`:

```python
@pytest.mark.asyncio
async def test_get_outcome_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/runs/nonexistent/outcome")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_outcome_after_create():
    from app.models import OutcomeLog
    async with async_session() as db:
        run = PipelineRun(
            repo_url="/tmp/test",
            feature_name="test outcome",
            requirements="test",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        outcome = OutcomeLog(
            run_id=run.id,
            total_duration_seconds=30.5,
            agent_durations={"pm": 10.0, "dev": 15.0},
            gate_scores={"criteria_met": 3},
            failure_agent=None,
            failure_category=None,
            failure_summary=None,
        )
        db.add(outcome)
        await db.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/runs/{run.id}/outcome")
    assert response.status_code == 200
    data = response.json()
    assert data["total_duration_seconds"] == 30.5
    assert data["agent_durations"]["pm"] == 10.0
    assert data["failure_agent"] is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_runs_api.py::test_get_outcome_not_found tests/test_runs_api.py::test_get_outcome_after_create -v`
Expected: FAIL — 404 (no route)

**Step 3: Add OutcomeResponse model and endpoint**

In `backend/app/routers/runs.py`, add import for OutcomeLog:

```python
from app.models import PipelineRun, AgentOutput, OutcomeLog
```

Add response model (after AgentOutputResponse):

```python
class OutcomeResponse(BaseModel):
    id: str
    run_id: str
    total_duration_seconds: float | None
    agent_durations: dict | None
    gate_scores: dict | None
    failure_agent: str | None
    failure_category: str | None
    failure_summary: str | None

    model_config = {"from_attributes": True}
```

Add endpoint (after list_outputs):

```python
@router.get("/{run_id}/outcome", response_model=OutcomeResponse)
async def get_outcome(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OutcomeLog).where(OutcomeLog.run_id == run_id)
    )
    outcome = result.scalar_one_or_none()
    if not outcome:
        raise HTTPException(status_code=404, detail="Outcome not found")
    return outcome
```

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/routers/runs.py backend/tests/test_runs_api.py
git commit -m "feat: add GET /api/runs/{id}/outcome endpoint"
```

---

## Task 5: Add stats endpoint

**Files:**
- Modify: `backend/app/routers/runs.py`
- Test: `backend/tests/test_runs_api.py`

**Step 1: Write failing test**

Add to `backend/tests/test_runs_api.py`:

```python
@pytest.mark.asyncio
async def test_get_stats():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_runs" in data
    assert "pass_rate" in data
    assert "avg_gate_score" in data
    assert "most_common_failure_agent" in data
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_runs_api.py::test_get_stats -v`
Expected: FAIL — 404

**Step 3: Add stats endpoint**

Note: This endpoint needs a separate router prefix. Add it to the same file but with a direct route:

In `backend/app/routers/runs.py`, add after imports:

```python
from sqlalchemy import func
```

Add at the bottom of the file:

```python
stats_router = APIRouter(prefix="/api", tags=["stats"])


class StatsResponse(BaseModel):
    total_runs: int
    passed: int
    failed: int
    errored: int
    pass_rate: float
    avg_gate_score: float | None
    most_common_failure_agent: str | None


@stats_router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    all_runs = await db.execute(select(PipelineRun))
    runs = all_runs.scalars().all()

    total = len(runs)
    passed = sum(1 for r in runs if r.status == "passed")
    failed = sum(1 for r in runs if r.status == "failed")
    errored = sum(1 for r in runs if r.status == "error")
    pass_rate = (passed / total * 100) if total > 0 else 0.0

    scores = [r.gate_score for r in runs if r.gate_score is not None]
    avg_score = sum(scores) / len(scores) if scores else None

    # Most common failure agent from OutcomeLog
    from app.models import OutcomeLog
    outcome_result = await db.execute(
        select(OutcomeLog.failure_agent)
        .where(OutcomeLog.failure_agent.isnot(None))
    )
    failure_agents = [r[0] for r in outcome_result.all()]
    most_common = max(set(failure_agents), key=failure_agents.count) if failure_agents else None

    return StatsResponse(
        total_runs=total,
        passed=passed,
        failed=failed,
        errored=errored,
        pass_rate=round(pass_rate, 1),
        avg_gate_score=round(avg_score, 1) if avg_score is not None else None,
        most_common_failure_agent=most_common,
    )
```

Then in `backend/app/main.py`, add the stats_router import and include:

```python
from app.routers.runs import router as runs_router, stats_router
# ...
app.include_router(stats_router)
```

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/routers/runs.py backend/app/main.py backend/tests/test_runs_api.py
git commit -m "feat: add GET /api/stats endpoint with run analytics"
```

---

## Task 6: Dashboard stats section

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Add stats interface and fetch**

In `frontend/src/pages/Dashboard.tsx`, add a Stats interface after the Run interface:

```typescript
interface Stats {
  total_runs: number
  passed: number
  failed: number
  errored: number
  pass_rate: number
  avg_gate_score: number | null
  most_common_failure_agent: string | null
}
```

Add stats state and fetch alongside the existing runs fetch:

```typescript
  const [stats, setStats] = useState<Stats | null>(null)
```

In the useEffect, add a parallel fetch:

```typescript
  useEffect(() => {
    Promise.all([
      fetch('/api/runs').then((r) => {
        if (!r.ok) throw new Error(`API error: ${r.status}`)
        return r.json()
      }),
      fetch('/api/stats').then((r) => r.ok ? r.json() : null),
    ])
      .then(([runsData, statsData]) => {
        setRuns(runsData)
        setStats(statsData)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
```

Note: This replaces the existing useEffect. The error state is from the make-it-work PR.

**Step 2: Add stats display**

After the `<h1>` and before the runs list conditional, add:

```typescript
      {stats && stats.total_runs > 0 && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-gray-800 p-3 text-center">
            <p className="text-2xl font-bold">{stats.total_runs}</p>
            <p className="text-xs text-gray-500">Total Runs</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-3 text-center">
            <p className="text-2xl font-bold text-green-400">{stats.pass_rate}%</p>
            <p className="text-xs text-gray-500">Pass Rate</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-3 text-center">
            <p className="text-2xl font-bold">{stats.avg_gate_score ?? '—'}</p>
            <p className="text-xs text-gray-500">Avg Gate Score</p>
          </div>
          <div className="rounded-lg border border-gray-800 p-3 text-center">
            <p className="text-2xl font-bold text-red-400">
              {stats.most_common_failure_agent ?? '—'}
            </p>
            <p className="text-xs text-gray-500">Top Failure Agent</p>
          </div>
        </div>
      )}
```

**Step 3: Type check and build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: Clean compile

**Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: add stats summary to Dashboard"
```

---

## Task 7: Delete stale DB and smoke test

Since we added a new model (`OutcomeLog`), the existing SQLite DB won't have the table. The app auto-creates tables on startup via `init_db()`.

**Step 1: Remove old database**

```bash
rm -f backend/solocarta.db
```

**Step 2: Start backend**

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload
```

Verify: `curl http://localhost:8000/health` returns `{"status":"ok"}`
Verify: `curl http://localhost:8000/api/stats` returns `{"total_runs":0,"passed":0,...}`

**Step 3: Start frontend**

```bash
cd frontend && npm run dev
```

Open http://localhost:5173 — should see Dashboard with empty state.

**Step 4: Create a test run via UI**

1. Click "Create one" link
2. Fill in:
   - Repo URL: `/Users/parker/Desktop/Dev/SoloCarta`
   - Feature Name: `add request logging middleware`
   - Requirements: `Add a FastAPI middleware that logs HTTP method, path, status code, and response time for every request. Add a unit test.`
3. Click "Start Pipeline"
4. Watch RunDetail page — SSE events should stream in

**Step 5: Observe and document**

Whether it succeeds or fails, check:
- `curl http://localhost:8000/api/runs` — run should exist with status
- `curl http://localhost:8000/api/runs/{id}/outcome` — outcome log should exist
- `curl http://localhost:8000/api/stats` — stats should reflect the run
- Dashboard should show stats cards

**Step 6: Commit any fixes needed**

If the smoke test reveals issues, fix them and commit.

---

## Verification

After all tasks:

1. `cd backend && python -m pytest tests/ -v` — all tests pass
2. `cd frontend && npx tsc --noEmit && npm run build` — compiles clean
3. Backend starts, frontend starts, stats endpoint returns data
4. At least one pipeline run attempted (success or failure — both produce useful outcome data)
