---
always: true
---

# Testing Rules

## CRITICAL: Tests Are Mandatory

**NEVER commit code without tests.**

**Minimum coverage: 80%**

### Unit Tests Required

Every service MUST have:
- Unit tests for core business logic
- Coverage ≥ 80%
- Mock all external dependencies

```python
# services/market-regime/tests/test_service.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_fingpt():
    with patch('src.utils.fingpt.FinGPT') as mock:
        mock.return_value.classify = AsyncMock(return_value={
            "regime": "crisis",
            "confidence": 0.95
        })
        yield mock

@pytest.mark.asyncio
async def test_regime_classification(mock_fingpt):
    service = MarketRegimeService()
    result = await service.get_current_regime()
    assert result.regime == "crisis"
```

### Mock External APIs

**ALWAYS mock**:
- FinGPT API
- Claude API
- Alpha Vantage API
- Database connections (in unit tests)

**NEVER call real APIs in tests.**

### Integration Tests

For cross-service communication:
- Test gRPC client-server interaction
- Use docker-compose to start services
- Clean up test data after each test

### Test Organization

```
services/market-regime/
├── tests/
│   ├── test_service.py        # Unit tests
│   └── test_integration.py    # Integration tests

tests/                          # Root-level
├── integration/                # Cross-service
└── e2e/                        # End-to-end
```

### Code Quality Checks

**ALWAYS run before commit:**

```bash
# Lint check (unused imports, code style)
ruff check [파일경로]

# Format check
ruff format --check [파일경로]
```

**Common issues caught by ruff:**
- Unused imports (F401)
- Unused variables (F841)
- Import sorting
- Line length violations

**QA must verify:** `ruff check` passes with no errors.

### Running Tests

Before every commit:

```bash
# Code quality (MUST pass)
ruff check shared/

# Unit tests
pytest services/market-regime/tests/ --cov=src --cov-fail-under=80

# Integration tests
pytest tests/integration/

# All tests
pytest --cov --cov-fail-under=80
```

### CI/CD Gate

**Tests MUST pass in CI before merge.**

All PRs require:
- [ ] `ruff check` passing (no lint errors)
- [ ] Unit tests passing
- [ ] Coverage ≥ 80%
- [ ] Integration tests passing
- [ ] No warnings or errors
