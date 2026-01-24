# Claude Code Configuration

BLOASIS Claude Code setup for development workflow.

## Structure

```
.claude/
├── README.md           # This file
├── skills/             # Reusable patterns and standards
│   ├── project-structure.md
│   ├── testing-standards.md
│   └── langgraph-patterns.md
├── rules/              # Always-follow guidelines (enforced)
│   ├── grpc.md
│   ├── testing.md
│   ├── architecture.md
│   └── security.md
├── commands/           # Slash commands for quick actions
│   ├── test.md
│   ├── service.md
│   └── deploy.md
└── contexts/           # Mode-specific prompts
    ├── worker.md
    ├── review.md
    └── debug.md
```

## Skills

**Reusable implementation patterns** that can be referenced when needed.

- **project-structure.md**: Folder hierarchy, naming conventions
- **testing-standards.md**: Test requirements and patterns
- **langgraph-patterns.md**: Multi-agent workflow patterns

**Usage**: Reference in implementation (e.g., "See `.claude/skills/testing-standards.md`")

**Note**: gRPC patterns and code guidelines are in `services/CLAUDE.md` with practical examples.

## Rules

**Always-enforced guidelines** that must be followed in all code.

- **grpc.md**: Internal services MUST use gRPC (not HTTP)
- **testing.md**: All code MUST have tests (≥80% coverage)
- **architecture.md**: Core architectural decisions (Redpanda, Python-only, etc.)
- **security.md**: Security requirements (no hardcoded secrets, Decimal for money, etc.)

**Enforcement**: Claude will check these before proceeding with implementation.

## Commands

**Slash commands** for common operations.

- `/test [service]`: Run tests with coverage
- `/service <name> <port>`: Create new service with boilerplate
- `/deploy <service>`: Verify deployment readiness

**Usage**: Type `/test` in Claude Code to run tests.

## Contexts

**Mode-specific prompts** for different work types.

- **worker.md**: Implementation mode (building features)
- **review.md**: Code review mode (verifying quality)
- **debug.md**: Debugging mode (diagnosing issues)

**Usage**: Activated automatically based on task context.

## Quick Reference

### Starting Implementation

1. Check current task in [docs/architecture/12-roadmap.md](../../docs/architecture/12-roadmap.md)
2. Review relevant architecture docs
3. Reference `.claude/skills/` for patterns
4. Follow `.claude/rules/` strictly
5. Use `/service` to generate boilerplate
6. Implement with tests
7. Verify with `/deploy`

### Code Review

1. Run automated checks (`.claude/contexts/review.md`)
2. Verify against `.claude/rules/`
3. Check test coverage (`/test`)
4. Approve or request changes

### Debugging

1. Collect logs and error messages
2. Follow `.claude/contexts/debug.md`
3. Use debugging tools (pdb, grpcurl, docker logs)
4. Add test to prevent regression

## Integration with Development

### Worker Session

When implementing:
```bash
# 1. Read task
cat docs/architecture/12-roadmap.md

# 2. Generate service
/service market-regime 50051

# 3. Implement
# (Follow .claude/skills/ patterns)

# 4. Test
/test market-regime

# 5. Verify
/deploy market-regime
```

### QA Session

When reviewing:
```bash
# 1. Check compliance
# (Follow .claude/contexts/review.md)

# 2. Run tests
/test

# 3. Security audit
grep -r "sk-\|api_key.*=" services/*/src/

# 4. Approve or reject
```

## Customization

This configuration is tailored for BLOASIS. Modify as needed:

- Add new skills for emerging patterns
- Update rules if architecture changes
- Create new commands for frequent operations
- Add contexts for new work modes

## Philosophy

1. **Consistency**: Follow established patterns
2. **Quality**: Never skip tests or security checks
3. **Speed**: Use commands to avoid repetitive work
4. **Documentation**: Skills are living documentation

---

**For detailed implementation guide**, see:
- [claude.md](../claude.md) - Project overview
- [services/CLAUDE.md](../services/CLAUDE.md) - Service implementation
