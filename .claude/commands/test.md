---
name: test
description: Run tests with coverage verification
---

# Test Command

Run tests for a service or the entire project with coverage requirements.

## Usage

```
/test [service-name]
```

## What This Does

1. **Run tests** for specified service or all services
2. **Check coverage** (minimum 80%)
3. **Report failures** with actionable feedback
4. **Verify mocks** for external APIs

## Implementation

### Single Service

```bash
# Run tests for market-regime service
cd services/market-regime
pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

### All Services

```bash
# Run all tests
pytest --cov --cov-report=term-missing --cov-fail-under=80
```

### Integration Tests

```bash
# Cross-service integration
pytest tests/integration/
```

### E2E Tests

```bash
# Full workflow tests
pytest tests/e2e/
```

## Coverage Requirements

- **Unit tests**: ≥ 80%
- **Core services** (Market Regime, AI Analysis): ≥ 80%
- **Utilities** (shared/utils): ≥ 90%

## Mock Verification

Ensure all external APIs are mocked:

```python
# Check for unmocked API calls
grep -r "requests\." services/*/src/ | grep -v test  # Should be empty
grep -r "httpx\." services/*/src/ | grep -v test    # Should be empty
```

## Output

The command should report:
- Tests passed/failed
- Coverage percentage
- Uncovered lines
- Missing mocks

## Example

```bash
$ /test market-regime

Running tests for market-regime service...

============================= test session starts ==============================
services/market-regime/tests/test_service.py ........                   [100%]

---------- coverage: platform darwin, python 3.11.6 -----------
Name                            Stmts   Miss  Cover   Missing
-------------------------------------------------------------
src/__init__.py                     0      0   100%
src/main.py                        45      3    93%   78-80
src/service.py                     67      5    93%   125-129
src/models.py                      34      2    94%   45-46
-------------------------------------------------------------
TOTAL                             146      10    93%

============================== 10 passed in 2.45s ==============================

✓ Coverage: 93% (threshold: 80%)
✓ All tests passed
```
