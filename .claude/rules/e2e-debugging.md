# E2E Debugging Rules

## CRITICAL: Flow-First Debugging

**NEVER chase error logs reactively. ALWAYS trace the full pipeline first.**

This rule exists because 4 debugging sessions were wasted fixing symptoms one-by-one instead of diagnosing the root cause in one pass.

### 1. Draw the Full Pipeline Before Touching Code

Before fixing anything, map out the entire data flow:

```
Frontend (Next.js) -> API Proxy (/api/[...path]) -> FastAPI Router -> Service -> core/ -> DB/Redis/LLM
```

For each hop, verify: **"Does data actually pass through here?"**

```bash
# Check FastAPI is running
curl http://localhost:8000/health

# Check Next.js proxy forwards correctly
curl http://localhost:3000/api/v1/health

# Check Redis has expected state
redis-cli keys "market:*"

# Check DB has expected rows
psql -h localhost -U postgres -d bloasis -c "SELECT count(*) FROM users;"
```

**Do NOT stop at the first error.** Map the full flow, identify ALL failure points, then fix them together.

### 2. "No Error" != "Working"

A module with zero error logs may be **doing nothing at all**.

Always verify **positive evidence of correct behavior**, not just absence of errors:

```bash
# BAD: "no errors in uvicorn log, must be fine"
# GOOD: "uvicorn log shows POST /v1/users/{id}/signals returned 200 with 15 signals"
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

**In-memory-only state that gets lost on restart is always a bug in production.**

### 4. Fix All Instances, Not Just One

When fixing a pattern (e.g., wrong config value, bad timeout), **sweep the entire codebase**:

```bash
# After fixing a timeout in one service method, check all similar timeouts:
grep -r "timeout=" app/ --include="*.py" | grep -v test

# After fixing a cache key format, check all cache keys:
grep -r "cache_key" app/ --include="*.py"
```

**A partial fix is worse than no fix** — it creates false confidence that the issue is resolved.

### 5. Verify Preconditions, Not Just Error Handlers

Before looking at exception handling, check:

1. **Is the request even reaching the router?** (Check uvicorn access log)
2. **Is the service method even called?** (Add/check entry log)
3. **Is the required state present?** (Redis key exists, DB row exists, config loaded)

Most "silent failures" are functions that never execute, not functions that throw errors.

### 6. Startup Recovery Checklist

When the FastAPI process restarts, verify:

- [ ] Does it reconnect to all dependencies? (Redis, PostgreSQL)
- [ ] Does lifespan startup complete without errors? (check uvicorn log)
- [ ] Are background tasks re-scheduled? (trading sessions, polling)
- [ ] Is Redis cache state still valid? (TTLs, stale data)

### 7. Debugging Order

Follow this order strictly. Do NOT skip to step 3.

```
Step 1: Map full E2E pipeline (Frontend -> Proxy -> Router -> Service -> core/)
Step 2: Verify each hop passes data (positive evidence, not "no errors")
Step 3: Identify ALL failure points (not just the first one)
Step 4: Check state persistence (Redis TTLs, DB rows, in-memory state)
Step 5: grep for the same pattern across the entire codebase
Step 6: Fix all issues together, test E2E once
```

### 8. Caching Debug Table

When data seems stale or missing, check the cache layer:

| Cache Key Pattern | TTL | Tier |
|---|---|---|
| `market:regime:current` | 6h | Tier 1 (shared) |
| `sector:analysis:{regime}` | 6h | Tier 1 (shared) |
| `user:{id}:stock_picks` | 1h | Tier 2 (per-user) |
| `user:{id}:preferences` | 30d | Tier 3 (per-user) |
| `user:{id}:portfolio` | 1h | Tier 3 (per-user) |

To force a fresh computation, delete the relevant cache key:
```bash
redis-cli del "market:regime:current"
```

### Anti-Patterns (DO NOT)

- **DO NOT** fix one error, restart, and wait for the next error to appear
- **DO NOT** assume "no error log = module is working correctly"
- **DO NOT** fix a config value in one file without grepping for all occurrences
- **DO NOT** debug by reading only error-level logs — read INFO logs to verify expected flow
- **DO NOT** skip state persistence analysis for any code that maintains runtime state
