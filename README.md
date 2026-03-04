# SoloCarta

An AI-powered development pipeline that turns feature requirements into pull requests. SoloCarta orchestrates a team of specialized AI agents — from product spec through code review — running in sandboxed workspaces with real-time visibility via a React dashboard.

## How It Works

```
Requirements → PM → Architect → Planner → Dev → QA → Reviewer → Gatekeeper → PR
```

Seven agents run sequentially via [LangGraph](https://github.com/langchain-ai/langgraph), each with a specific role and tool access level. The pipeline operates in an isolated copy of your repo, and only creates a PR if the Gatekeeper scores the implementation above threshold.

| Agent | Role | Tools |
|-------|------|-------|
| PM | Converts requirements into a testable spec | Read-only |
| Architect | Determines technical approach | Read-only |
| Planner | Breaks architecture into ordered tasks | Read-only |
| Dev | Implements code changes and tests | Read, Write, Edit, Bash |
| QA | Runs lint, tests, type checks | Read, Bash |
| Reviewer | Evaluates implementation quality | Read-only |
| Gatekeeper | Scores rubric, decides PASS/FAIL | Read-only |

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy (async SQLite), LangGraph
- **Agent Runtime:** [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS
- **Streaming:** Server-Sent Events (SSE) for real-time pipeline updates

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- An [Anthropic API key](https://console.anthropic.com/)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create a `.env` file in the project root:

```env
SOLOCARTA_ANTHROPIC_API_KEY=sk-ant-...
SOLOCARTA_GITHUB_TOKEN=ghp_...  # optional, for PR creation
```

Start the server:

```bash
uvicorn app.main:app --reload
```

The API is available at http://localhost:8000 with Swagger docs at http://localhost:8000/docs.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 to access the dashboard.

### Run Tests

```bash
cd backend
source .venv/bin/activate
python -m pytest tests/ -v
```

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app with lifespan
│   ├── config.py             # Pydantic settings
│   ├── database.py           # Async SQLAlchemy setup
│   ├── models.py             # PipelineRun, AgentOutput models
│   ├── engine/
│   │   ├── orchestrator.py   # LangGraph pipeline (10 nodes)
│   │   ├── claude_runtime.py # Agent SDK wrapper
│   │   ├── sandbox.py        # Isolated workspace creation
│   │   ├── runner.py         # Background pipeline execution
│   │   └── github.py         # Branch push + PR creation
│   ├── prompts/              # Agent prompt templates (7 .md files)
│   └── routers/
│       ├── runs.py           # CRUD endpoints for pipeline runs
│       └── stream.py         # SSE streaming endpoint
└── tests/
frontend/
├── src/
│   ├── App.tsx               # Routing + layout
│   ├── pages/
│   │   ├── Dashboard.tsx     # Pipeline run list
│   │   ├── NewRun.tsx        # Create + start pipeline
│   │   └── RunDetail.tsx     # Real-time pipeline view
│   ├── hooks/useSSE.ts       # Server-Sent Events hook
│   └── components/
│       ├── PipelineTimeline.tsx
│       └── AgentCard.tsx
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to get involved.

## License

[MIT](LICENSE)
