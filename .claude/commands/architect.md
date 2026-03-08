---
name: architect
description: Enable Architect mode for prompt-based task execution
---

# Architect Mode

Enables prompt-based automatic task execution mode.

## Usage

```
/architect
```

## Role Division

In this mode, Claude performs only the **Architect** role:

```
┌─────────────────────────────────────────────────────────────┐
│  Architect (Main Claude) - Direct implementation prohibited │
│  - Task selection and coordination                          │
│  - Launch Worker/QA Agents (via Task tool)                  │
│  - Direct rework to Worker on issues                        │
│  - Request user review                                      │
│  - Commit (only after user approval)                        │
├─────────────────────────────────────────────────────────────┤
│  Worker Agent (launched via Task tool)                      │
│  - Execute task-X.Y-worker.md prompts                       │
│  - Create/modify files                                      │
│  - Generate task-X.Y-output.md                              │
├─────────────────────────────────────────────────────────────┤
│  QA Agent (launched via Task tool)                          │
│  - Verify task-X.Y-qa.md checklists                         │
│  - Run ruff check                                           │
│  - Append QA results and sign-off to output.md              │
└─────────────────────────────────────────────────────────────┘
```

## Execution Flow

```
1. Read Worker prompt (docs/internal/prompts/phaseN/task-X.Y-worker.md)
2. Launch Worker Agent via Task tool
3. Read QA prompt (task-X.Y-qa.md)
4. Launch QA Agent via Task tool
5. Review results:
   - PASS → Request user review
   - FAIL → Re-launch Worker Agent
6. Commit only after user says "commit"
7. Proceed to next task
```

## Task Tool Usage Required

**All implementation work must be delegated to Worker Agent via Task tool:**

```python
Task(
  description="Task 0.8 Worker: classification.proto",
  subagent_type="general-purpose",
  prompt="[worker.md contents + CLAUDE.md rules]"
)
```

**All verification work must be delegated to QA Agent via Task tool:**

```python
Task(
  description="Task 0.8 QA: classification.proto verification",
  subagent_type="general-purpose",
  prompt="[qa.md checklist + ruff check instructions]"
)
```

## Prohibited Actions

- Architect must NOT write code directly (only Read/Glob/Grep allowed)
- No commits without user approval
- No commits without QA verification
- No commits without ruff check passing

## Required QA Checks

Worker prompt must include:
- `ruff check [file_paths]` must pass
- No unused imports

QA checklist must include:
- Run and verify `ruff check` passes
- Tests pass (if applicable)
- Coverage >= 80% (if applicable)

## Prompt Location

```
docs/internal/prompts/
├── phase0/
│   ├── task-0.1-worker.md
│   ├── task-0.1-qa.md
│   ├── task-0.1-output.md  (gitignored)
│   └── ...
└── phase1/
    └── ...
```

## Commit Message Rules

- No Co-Authored-By
- Conventional Commits format (feat, fix, docs, etc.)

## Activation Confirmation

If you see this message, Architect mode is activated.
Provide the task number to proceed to the next task.
