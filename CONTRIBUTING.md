# Contributing to SoloCarta

Thanks for your interest in contributing! This guide will help you get started.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/<your-username>/SoloCarta.git`
3. Create a branch: `git checkout -b feature/your-feature`
4. Follow the [Quick Start](#quick-start) in the README to set up your environment

## Development Workflow

### Branch Naming

- `feature/description` — new functionality
- `fix/description` — bug fixes
- `docs/description` — documentation changes
- `refactor/description` — code improvements without behavior change

### Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add SSE heartbeat to prevent connection timeouts
fix: validate run_id exists before opening SSE stream
docs: add API endpoint documentation
test: add integration test for pipeline runner
refactor: extract shared test fixtures into conftest
```

### Pull Requests

1. Keep PRs focused — one feature or fix per PR
2. Include tests for new behavior
3. Update the README if you change public APIs or setup steps
4. Ensure all tests pass before submitting
5. Write a clear description of what changed and why

## Running Tests

### Backend

```bash
cd backend
source .venv/bin/activate
python -m pytest tests/ -v
```

### Frontend

```bash
cd frontend
npm run build   # type-check + build
```

## Code Style

### Python (Backend)

- Follow existing patterns in the codebase
- Use type hints
- Async where the framework expects it (FastAPI endpoints, SQLAlchemy queries)
- Keep functions focused and small

### TypeScript (Frontend)

- Functional components with hooks
- TypeScript strict mode (via `tsconfig.json`)
- Tailwind for styling — no CSS modules or styled-components

## Reporting Issues

When filing an issue, please include:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Python/Node versions and OS

## Questions?

Open a [Discussion](https://github.com/ParkerQIV/SoloCarta/discussions) for questions that aren't bug reports or feature requests.
