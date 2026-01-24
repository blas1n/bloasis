---
context: worker
description: Implementation mode - building features and services
---

# Worker Context

You are implementing BLOASIS services. Focus on clean, tested code.

## Current Phase

Phase 1: Core Trading Logic (US Stocks only)

**Reference**: [docs/architecture/12-roadmap.md](../../docs/architecture/12-roadmap.md)

## Your Role

1. **Implement tasks** from roadmap
2. **Write tests** alongside code (80%+ coverage)
3. **Follow standards** in `.claude/skills/`
4. **Ask questions** when requirements unclear

## Before You Start

Read:
- Task definition in roadmap
- Relevant architecture docs
- Related skills (`.claude/skills/`)

## Implementation Pattern

1. **Create service structure** (if new)
2. **Define .proto** with HTTP annotations
3. **Implement business logic** in src/service.py
4. **Write unit tests** in tests/
5. **Add integration tests** if cross-service
6. **Verify with** `/deploy <service>`

## Critical Rules

Always follow `.claude/rules/`:
- **gRPC only** for internal communication
- **Redpanda** for events (not Redis Pub/Sub)
- **Type hints** required
- **Tests required** (80%+ coverage)
- **Decimal for money**
- **Proto HTTP annotations**

## Code Quality

Before committing:
- [ ] Type hints on all functions
- [ ] Tests written and passing
- [ ] External APIs mocked
- [ ] gRPC errors handled
- [ ] No hardcoded secrets
- [ ] Structured logging used

## Reference Documents

- `.claude/skills/testing-standards.md`: Testing patterns
- `.claude/skills/langgraph-patterns.md`: Multi-agent workflows
- `services/CLAUDE.md`: Service implementation (gRPC, coding patterns, examples)

## Communication

- **Progress**: Update todos
- **Blockers**: Ask questions immediately
- **Decisions**: Document in code comments
- **Completion**: Run `/deploy <service>` checklist
