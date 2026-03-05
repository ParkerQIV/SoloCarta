# Retry Logic on Gate FAIL

## Summary

When the gatekeeper returns FAIL, loop back through dev -> qa -> reviewer -> gatekeeper instead of terminating. Dev receives the gatekeeper's failure reasons and reviewer report as context for the fix attempt.

## Design

### PipelineState — new fields

```python
retry_count: int          # current attempt (starts at 0, incremented on each retry)
max_retries: int          # configurable per-run, default 2
gate_feedback: str | None # gatekeeper reasons passed back to dev on retry
```

### Orchestrator — 3-way conditional routing

`route_gate_result` becomes:
- PASS -> `create_pr`
- FAIL + `retry_count < max_retries` -> `dev` (loop back)
- FAIL + `retry_count >= max_retries` -> `fail`

The gatekeeper node sets `gate_feedback` from its decision reasons and increments `retry_count`.

### Dev node — retry-aware context

When `retry_count > 0`, dev receives additional context:

```
Previous attempt failed. Gatekeeper feedback:
{gate_feedback}

Reviewer report:
{review_report}

Fix the issues and try again.
```

### API — max_retries parameter

Add optional `max_retries` field to the create-run request body (default 2). Stored on the PipelineRun model.

### Runner/SSE — retry events

Emit a `retry` SSE event when looping back so the frontend can display retry status. The existing `_run_graph_streaming` handles nodes running multiple times since LangGraph streams each execution.

### Frontend — retry display

When a `retry` SSE event arrives, show a "Retry N/M" indicator. Existing AgentCard components handle re-running agents via `agent_start`/`agent_complete` events.

### Testing

- Unit: `route_gate_result` with retries remaining -> routes to "dev"
- Unit: `route_gate_result` with no retries -> routes to "fail"
- Unit: dev node context includes gate_feedback when retry_count > 0
- Integration: mock FAIL-then-PASS sequence through the graph
