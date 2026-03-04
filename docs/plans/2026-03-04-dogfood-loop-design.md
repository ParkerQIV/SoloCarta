# Dogfood Loop — Design

> Use SoloCarta on itself: build loop first, then self-improvement.

**Approach:** Minimal viable dogfood (A), with data model designed for future improvement loop (B).

---

## Phase A: Get It Running on Itself

### 1. Prerequisites

Merge PR #1 (`feature/make-it-work`) into main. Smoke test: start backend + frontend, create a run, verify infrastructure works (pipeline starts, SSE streams, errors surface in UI).

### 2. Outcome Logging

Add an `OutcomeLog` model to capture structured data from every completed run.

**Schema:**

```
OutcomeLog
├── id (UUID, PK)
├── run_id (FK → pipeline_runs.id, unique)
├── total_duration_seconds (Float)
├── agent_durations (JSON: {"pm": 12.3, "architect": 8.1, ...})
├── gate_scores (JSON: {"criteria_met": 3, "tests_pass": 2, ...})
├── failure_agent (String | null — which agent failed)
├── failure_category (String | null — timeout | bad_output | test_failure | gate_fail | crash | cancelled)
├── failure_summary (Text | null — one-line human-readable)
├── created_at (DateTime)
```

**Why this schema:** Supports future queries like "which agent fails most?", "what's our pass rate?", "average duration by agent" without schema changes. The JSON fields for durations and scores are flexible enough for the gate rubric to evolve.

**API:** `GET /api/runs/{id}/outcome` — returns OutcomeLog with all AgentOutput records inlined.

### 3. Runner Integration

In `execute_pipeline()`, after the pipeline completes (success, error, or cancellation), create an OutcomeLog record:

- **Success path:** Calculate total duration from run timestamps. Per-agent durations from AgentOutput `started_at`/`completed_at`. Gate scores from `gate_result` JSON. `failure_agent=null`.
- **Error path:** Record partial data. Set `failure_agent` to the agent that errored (from `AgentError.agent_name`). Categorize: `timeout` if TimeoutError, `crash` otherwise. `failure_summary` from exception message.
- **Cancellation:** `failure_category="cancelled"`, record whatever data exists.

### 4. First Dogfood Run

Point SoloCarta at its own repo with a small, well-scoped feature:

```
Repo: /Users/parker/Desktop/Dev/SoloCarta
Feature: Add request logging middleware
Requirements: Add a FastAPI middleware that logs HTTP method, path,
              status code, and response time for every request.
              Add a unit test for the middleware.
```

**Why this feature:**
- Small enough for agents to handle
- Touches real code (backend/app/main.py)
- Clear acceptance criteria
- If it fails, the outcome log tells us exactly where

### 5. Dashboard Stats

Add a stats section to the Dashboard page showing:
- Total runs / pass rate / average gate score
- Most common failure agent (if any)
- Last 5 runs with status

Data comes from aggregate queries on PipelineRun + OutcomeLog. Lightweight — no new infrastructure.

---

## Phase B: Improvement Loop (Future)

Once we have 10+ runs with outcome data:

1. **Postmortem agent** — analyzes OutcomeLog after failed runs, identifies root cause, suggests prompt patches
2. **Prompt versioning** — each prompt file gets a version, patches create new versions
3. **Auto-retry with feedback** — when gatekeeper fails, feed reviewer critique back to dev and re-run (not whole pipeline)
4. **Agent performance dashboard** — per-agent pass rates, duration trends, failure categories over time

Phase B is designed but NOT built yet. The OutcomeLog schema supports it without changes.

---

## Success Criteria

**Phase A is done when:**
1. PR #1 merged, backend + frontend start clean
2. OutcomeLog model exists, runner creates records automatically
3. `GET /api/runs/{id}/outcome` returns structured data
4. Dashboard shows basic stats
5. One real dogfood run completes (success or failure — either is useful data)

**Phase B is done when:**
- Postmortem agent produces actionable prompt patches after failures
- Pass rate trends upward over 10+ runs
