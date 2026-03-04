# SoloCarta MVP Design
### Date: 2026-03-04
### Status: Approved

---

## 1. What is SoloCarta

A standalone product (web dashboard + backend) that automates the software development lifecycle using specialized AI agents. Point it at any repo, provide requirements, and it generates a PR — spec through implementation through review.

**Target user:** Solo technical founder / product owner.

**Human role:** Provide requirements, approve final PRs.

---

## 2. Architecture

```
React Dashboard (Vite + Tailwind)
        │ REST API + SSE
FastAPI Backend
        │
   ┌────┴────┐
   │         │
LangGraph  SQLite
Engine     (SQLAlchemy)
   │
Claude Agent SDK
   │
Sandbox Engine (.workspaces/<run_id>/)
   │
GitHub Integration (push branch, create PR)
```

### Key decisions

- **SQLite** to start — single file, no infra. Migrate to PostgreSQL later if needed.
- **SSE** for real-time pipeline updates — simpler than WebSockets, sufficient for one-directional streaming.
- **asyncio background tasks** — no Celery/Redis at this scale.
- **Agent prompts as .md files** — easy to read, edit, version.

---

## 3. Project Structure

```
solocarta/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry
│   │   ├── config.py               # Settings
│   │   ├── models.py               # SQLAlchemy models
│   │   ├── database.py             # DB connection/session
│   │   ├── routers/
│   │   │   ├── runs.py             # Pipeline run CRUD + trigger
│   │   │   ├── repos.py            # Repo configuration
│   │   │   ├── agents.py           # Agent output/log viewing
│   │   │   └── stream.py           # SSE streaming endpoint
│   │   ├── engine/
│   │   │   ├── orchestrator.py     # LangGraph state machine
│   │   │   ├── sandbox.py          # Workspace creation/cleanup
│   │   │   ├── claude_runtime.py   # Claude Agent SDK wrapper
│   │   │   └── github.py           # Push branch + create PR
│   │   ├── agents/
│   │   │   ├── pm.py
│   │   │   ├── architect.py
│   │   │   ├── planner.py
│   │   │   ├── dev.py
│   │   │   ├── qa.py
│   │   │   ├── reviewer.py
│   │   │   └── gatekeeper.py
│   │   └── prompts/
│   │       ├── pm.md
│   │       ├── architect.md
│   │       ├── planner.md
│   │       ├── dev.md
│   │       ├── qa.md
│   │       ├── reviewer.md
│   │       └── gatekeeper.md
│   ├── requirements.txt
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── NewRun.tsx
│   │   │   ├── RunDetail.tsx
│   │   │   └── Settings.tsx
│   │   ├── components/
│   │   │   ├── AgentCard.tsx
│   │   │   ├── PipelineTimeline.tsx
│   │   │   ├── DiffViewer.tsx
│   │   │   └── LogViewer.tsx
│   │   └── hooks/
│   │       └── useSSE.ts
│   ├── package.json
│   └── vite.config.ts
├── docs/
│   └── plans/
└── README.md
```

---

## 4. Pipeline Data Flow

### Starting a run

1. User submits: repo URL, branch, feature name, requirements
2. Backend creates `PipelineRun` record (status: `pending`)
3. Background task starts LangGraph state machine
4. SSE streams status updates to dashboard

### LangGraph State

```python
class PipelineState(TypedDict):
    run_id: str
    repo_url: str
    base_branch: str
    sandbox_path: str
    feature_name: str
    requirements: str
    spec: str | None
    architecture: str | None
    plan: str | None
    implementation_summary: str | None
    qa_results: dict | None
    review_report: str | None
    gate_result: dict | None
    current_step: str
    status: str
    error: str | None
```

### Pipeline steps (sequential)

```
sandbox_setup → pm → architect → planner → dev → qa → reviewer → gatekeeper
                                                                      │
                                                          ┌───────────┴───────────┐
                                                        PASS                    FAIL
                                                          │                       │
                                                     create PR            log outcome
```

### Each agent step

1. Load prompt template from `prompts/<agent>.md`
2. Inject context (spec, architecture, etc.) into prompt
3. Call Claude Agent SDK scoped to sandbox workspace
4. Capture structured output
5. Store in `PipelineState` + `AgentOutput` DB record
6. Emit SSE event

---

## 5. Phase 1 Agents

| Agent | Input | Output |
|-------|-------|--------|
| PM | requirements, known pitfalls | spec, acceptance criteria, edge cases |
| Architect | spec, conventions | architecture notes, API/data changes, risks |
| Planner | spec, architecture | ordered tasks, dependencies, done criteria |
| Dev | spec, architecture, plan, conventions | code changes in sandbox, summary |
| QA | sandbox state | lint/test results, stdout/stderr, return codes |
| Reviewer | spec, architecture, QA results | review report, required changes |
| Gatekeeper | rubric, all outputs | score, PASS/FAIL, reasons |

---

## 6. Phase 2: Improvement Loop (Future)

Triggered on FAIL. Agents: Postmortem, Prompt Engineer, Evaluator.

Flow: Outcome log → root cause analysis → prompt patch proposal → evaluation → PR for prompt updates.

Deferred until 10-20 pipeline runs generate sufficient failure data.

---

## 7. Tech Stack Summary

| Layer | Technology |
|-------|-----------|
| Frontend | React, Vite, TypeScript, TailwindCSS |
| Backend API | FastAPI, Python |
| Orchestrator | LangGraph |
| Agent Runtime | Claude Agent SDK |
| Database | SQLite + SQLAlchemy |
| GitHub | gh CLI or PyGithub |
| Sandbox | shutil + git (Python) |

---

## 8. Roadmap

| Phase | Scope |
|-------|-------|
| Phase 1 | Core pipeline (7 agents) + web dashboard + sandbox + GitHub PR |
| Phase 1.5 | Telegram bot for remote access (kick off runs, check status, approve PRs) |
| Phase 2 | Self-improvement loop (Postmortem, Prompt Engineer, Evaluator agents) |
| Phase 3 | Parallel agent execution |

## 9. Out of Scope (Phase 1)

- Improvement loop (Phase 2)
- Telegram bot (Phase 1.5)
- Parallel agent execution (Phase 3)
- Auth / multi-user
- Deployment automation
- Model training
