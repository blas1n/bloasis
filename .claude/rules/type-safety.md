# Type Safety Rules

## CRITICAL: mypy Strict Mode

**After ANY Python code change, you MUST run mypy before considering the task complete:**

```bash
mypy app/ shared/
```

mypy strict is configured in `pyproject.toml`. All 57 source files must pass with zero errors.

Common fixes:
- Bare `dict`, `list`, `Callable` → parameterized (`dict[str, Any]`, `list[str]`, `Callable[..., Any]`)
- All public functions need return type annotations
- Enum values from DB/external sources need explicit casts (`RiskProfile(value)`, `OrderSide(value)`)

## CRITICAL: OpenAPI Schema Sync

**After changing response models (`app/core/responses.py`) or router signatures (`app/routers/*.py`), you MUST regenerate:**

```bash
# 1. Export OpenAPI schema
PYTHONPATH=/workspace python scripts/export_openapi.py

# 2. Regenerate frontend types
cd frontend && npm run generate:api

# 3. Verify frontend types compile
cd frontend && npm run type-check
```

This maintains the type pipeline: Python types → OpenAPI schema → TypeScript types.

## Response Models

- All response models inherit from `CamelModel` (`app/core/responses.py`) which accepts both snake_case and camelCase keys via `alias_generator`
- `CamelJSONResponse` converts snake_case → camelCase in HTTP responses
- Python `Decimal` fields serialize as JSON strings — frontend uses `Number()` for comparisons/arithmetic
