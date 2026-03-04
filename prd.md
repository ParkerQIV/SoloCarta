# PRD: Self-Improving AI Development Team (Python + Sandbox Workspace)

## 1. Overview

### 1.1 Purpose
Build a fully automated, agent-driven software development pipeline where the human (Parker) only:
1) provides requirements/context (first step) and  
2) performs final approval/review (last step).

All intermediate phases (spec → design → planning → implementation → QA → review → gating → PR creation) are executed by specialized AI agents orchestrated by a Python workflow engine, operating in an isolated sandbox workspace (copy repo → modify → test → open PR).

### 1.2 Goal
Create a “self-improving” AI dev team that continuously improves by:
- logging outcomes and failures,
- generating postmortems,
- proposing prompt/checklist patches to the AI team’s operating system (`/ai-team`),
- running evaluations to validate improvements,
- committing improvements via PRs for human approval.

### 1.3 Non-Goals
- Fully autonomous merges to main without human involvement.
- Fine-tuning or model training; improvements are made through prompt/rubric/checklist evolution.
- Production deployments (can be added later).

---

## 2. Success Metrics

### 2.1 Quality & Reliability
- ≥ 90% of PRs pass Gatekeeper criteria without human rework after 10–20 runs.
- Reduction in repeated failure causes (same root-cause category) over time.
- All merged PRs satisfy acceptance criteria and include tests when behavior changes.

### 2.2 Velocity
- Ability to generate a PR end-to-end from a requirement request with minimal human input.
- Parallelizable execution for multi-agent tasks (future enhancement).

### 2.3 Governance
- Every change is tracked via git commits and PRs.
- Sandboxed execution prevents unintended changes to the main working directory.

---

## 3. System Architecture

### 3.1 High-Level Components
1) **Orchestrator (Python + LangGraph)**
   - Deterministic workflow: step-by-step state machine.
   - Conditional routing: PASS → PR creation, FAIL → improvement loop.

2) **Sandbox Workspace Engine**
   - Creates isolated workspaces by copying repo into `.workspaces/<run_id>/`.
   - Copies `.git` into sandbox to support branching/commits.

3) **AI Team OS (`/ai-team`)**
   - Agent prompts (role definitions, checklists, constraints).
   - Rubrics for scoring output quality.
   - Memory files (conventions, known pitfalls, decisions log).
   - Outcome logs generated automatically.

4) **Agent Runtime (Claude Code / Agent SDK)**
   - Executes agent tasks inside the sandbox workspace.
   - Performs repo edits, runs commands, iterates.

5) **Quality Gate**
   - Runs lint/tests/type checks.
   - Gatekeeper agent scores rubric and decides PASS/FAIL.

6) **Improvement Loop**
   - Writes outcome logs.
   - Postmortem agent diagnoses failure.
   - Prompt Engineer agent proposes prompt/checklist patches.
   - Evaluator agent assesses patch usefulness and side effects.
   - (Phase 2) Patch Applier applies changes and opens PR for `/ai-team`.

---

## 4. Workflow Requirements

### 4.1 Build Loop (Every Feature)
#### Step 0 — Sandbox Setup
- Create workspace: `.workspaces/<run_id>/`
- Copy repository contents excluding `.venv`, `.workspaces`, and optionally large artifacts.
- Copy `.git` into sandbox.
- `git checkout <BASE_BRANCH>`
- `git checkout -b <AI_BRANCH_NAME>`

#### Step 1 — Product Manager Agent (PM)
Input:
- Feature name
- Requirements/context
- Known pitfalls
Output:
- `spec` with:
  - scope
  - acceptance criteria
  - edge cases
  - constraints/assumptions

#### Step 2 — Architect Agent
Input:
- spec
- conventions
Output:
- `architecture` notes:
  - API changes
  - data model changes
  - migrations
  - risks

#### Step 3 — Planner Agent
Input:
- spec
- architecture
Output:
- `plan`:
  - ordered tasks
  - done criteria per task
  - dependencies

#### Step 4 — Dev Agent (Implementation)
Input:
- spec
- architecture
- plan
- conventions
- known pitfalls
Actions:
- implement code changes in sandbox
- run `git status`
- run lint + tests
Output:
- implementation complete in code
- summary and risks

#### Step 5 — Quality Execution
- Run lint command (configurable)
- Run tests command (configurable)
- Capture stdout/stderr/return codes

#### Step 6 — Reviewer Agent
Input:
- spec
- architecture
- test/lint results
- summary (optional)
Output:
- review report:
  - correctness gaps
  - missing edge cases
  - security/perf risks
  - required changes

#### Step 7 — Gatekeeper Agent
Input:
- rubric
- spec
- architecture
- quality reports
- reviewer report
Output (JSON only):
```json
{
  "score": 12,
  "decision": "PASS",
  "reasons": ["..."],
  "required_fixes": ["..."]
}