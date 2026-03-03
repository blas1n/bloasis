# E2E Debugging Rules

## CRITICAL: Flow-First Debugging

**NEVER chase error logs reactively. ALWAYS trace the full pipeline first.**

This rule exists because 4 debugging sessions were wasted fixing symptoms one-by-one instead of diagnosing the root cause in one pass.

### 1. Draw the Full Pipeline Before Touching Code

Before fixing anything, map out the entire data flow:

```
Frontend → Envoy → Service A → Redpanda → Service B → Service C → External API → back
```

For each hop, verify: **"Does data actually pass through here?"**

```bash
# Check each service is running and listening
# Check Redpanda topics have expected messages
# Check Redis/DB has expected state
# Check external APIs are reachable
```

**Do NOT stop at the first error.** Map the full flow, identify ALL failure points, then fix them together.

### 2. "No Error" != "Working"

A service with zero error logs may be **doing nothing at all**.

Always verify **positive evidence of correct behavior**, not just absence of errors:

```bash
# BAD: "no errors in executor log, must be fine"
# GOOD: "executor log shows periodic_analysis triggered at 09:00, 09:10, 09:20"
```

Ask: **"What SHOULD I see in the logs if this is working correctly?"**
Then grep for that expected output. If it's missing, that's your bug.

### 3. State Persistence Check

For any stateful operation, immediately ask: **"Where is this state persisted?"**

| Answer | Risk |
|---|---|
| In-memory dict only | Lost on restart. Needs Redis/DB persistence. |
| Redis | Survives restart. Check TTL and key format. |
| PostgreSQL | Durable. Check if schema exists. |

**In-memory-only state in a service that gets restarted is always a bug in production.**

### 4. Fix All Instances, Not Just One

When fixing a pattern (e.g., wrong config value, bad timeout), **sweep the entire codebase**:

```bash
# After fixing keepalive in one file, find ALL occurrences:
grep -r "keepalive_time_ms.*10000" services/

# After fixing a timeout, check all similar timeouts:
grep -r "timeout=" services/ --include="*.py" | grep -v test
```

**A partial fix is worse than no fix** — it creates false confidence that the issue is resolved.

### 5. Verify Preconditions, Not Just Error Handlers

Before looking at exception handling, check:

1. **Is the triggering event even received?** (Redpanda consumer offset, gRPC call log)
2. **Is the function even called?** (Add/check entry log)
3. **Is the required state present?** (Redis key exists, DB row exists, config loaded)

Most "silent failures" are functions that never execute, not functions that throw errors.

### 6. Startup Recovery Checklist

When a service restarts, verify:

- [ ] Does it reconnect to all dependencies? (Redis, Postgres, Redpanda, gRPC peers)
- [ ] Does it recover in-flight state? (active tasks, pending operations)
- [ ] Does it re-register with service discovery? (Consul, health checks)
- [ ] Can Redpanda consumer groups pick up where they left off? (committed offsets vs new events)
- [ ] Are there any one-time events that won't be replayed? (e.g., "started" event already consumed)

### 7. Debugging Order

Follow this order strictly. Do NOT skip to step 3.

```
Step 1: Map full E2E pipeline (all hops, all services)
Step 2: Verify each hop passes data (positive evidence, not "no errors")
Step 3: Identify ALL failure points (not just the first one)
Step 4: Check state persistence for each stateful service
Step 5: grep for the same pattern across the entire codebase
Step 6: Fix all issues together, test E2E once
```

### 8. Timeout Chain Validation

In a cascading gRPC call chain, timeouts MUST be ordered:

```
Outer caller (longest) > Middle service > Inner service (shortest)

Example:
Executor → Strategy (900s) > Strategy → Classification (300s) > Classification → LLM (120s)
```

If inner timeout > outer timeout, the outer caller will DEADLINE_EXCEEDED before the inner call completes. **Check the entire chain, not just one hop.**

### Anti-Patterns (DO NOT)

- **DO NOT** fix one error, restart, and wait for the next error to appear
- **DO NOT** assume "no error log = service is working correctly"
- **DO NOT** fix a config value in one file without grepping for all occurrences
- **DO NOT** debug by reading only error-level logs — read INFO logs to verify expected flow
- **DO NOT** skip state persistence analysis for any service that maintains runtime state
