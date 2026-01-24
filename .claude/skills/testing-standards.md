---
name: testing-standards
description: Testing guidelines and coverage standards for BLOASIS
---

# Testing Standards Skill

## Test Structure

```
services/market-regime/
├── tests/
│   ├── test_service.py         # Unit tests
│   └── test_integration.py     # Integration tests

tests/                          # Root-level tests
├── integration/                # Cross-service integration
│   ├── test_market_regime_flow.py
│   └── test_ai_analysis_flow.py
└── e2e/                        # End-to-end tests
    └── test_complete_trading_cycle.py
```

## Test Types

### Unit Tests (per-service)

**Purpose**: Test individual functions/classes in isolation

**Location**: `services/{service}/tests/test_*.py`

**Example**:
```python
# services/market-regime/tests/test_service.py
import pytest
from src.service import MarketRegimeService

@pytest.fixture
def service():
    return MarketRegimeService()

def test_regime_classification(service):
    result = service.classify(mock_data)
    assert result.regime == "crisis"
    assert result.confidence > 0.8
```

**Coverage target**: 80%+

---

### Integration Tests (cross-service)

**Purpose**: Test service interactions via gRPC

**Location**: `tests/integration/test_*.py`

**Example**:
```python
# tests/integration/test_ai_analysis_flow.py
import pytest
import grpc

@pytest.mark.asyncio
async def test_full_analysis_pipeline():
    # Start services (docker-compose)
    async with grpc.aio.insecure_channel('localhost:50051') as channel:
        regime_stub = MarketRegimeStub(channel)
        regime = await regime_stub.GetCurrentRegime(RegimeRequest())

    async with grpc.aio.insecure_channel('localhost:50052') as channel:
        ai_stub = AIAnalysisStub(channel)
        analysis = await ai_stub.Analyze(AnalysisRequest(regime=regime.regime))

    assert analysis.strategy is not None
```

**Coverage target**: Critical paths only

---

### E2E Tests (full system)

**Purpose**: Test complete user workflows

**Location**: `tests/e2e/test_*.py`

**Example**:
```python
# tests/e2e/test_complete_trading_cycle.py
import pytest

@pytest.mark.asyncio
async def test_complete_trading_cycle():
    # 1. Trigger regime change
    await trigger_regime_change("crisis")

    # 2. Verify strategy generation
    strategy = await poll_strategy_service()
    assert strategy.defensive == True

    # 3. Verify backtest execution
    result = await poll_backtest_result()
    assert result.sharpe_ratio > 2.5

    # 4. Verify order execution
    orders = await poll_executor_service()
    assert len(orders) > 0
```

**Coverage target**: Core workflows only

---

## Testing Patterns

### Mock External APIs

```python
import pytest
from unittest.mock import patch, AsyncMock

@pytest.fixture
def mock_fingpt():
    with patch('src.utils.fingpt.FinGPT') as mock:
        mock.return_value.classify = AsyncMock(return_value={
            "regime": "crisis",
            "confidence": 0.95
        })
        yield mock

def test_with_mocked_fingpt(mock_fingpt):
    service = MarketRegimeService()
    result = await service.get_current_regime()
    assert result.regime == "crisis"
```

### Test Fixtures

```python
import pytest
from sqlalchemy import create_engine
from shared.models.risk_profile import RiskProfile

@pytest.fixture(scope="session")
def test_db():
    engine = create_engine("postgresql://test:test@localhost/test_db")
    # Setup tables
    Base.metadata.create_all(engine)
    yield engine
    # Teardown
    Base.metadata.drop_all(engine)

@pytest.fixture
def sample_profile():
    return RiskProfile(
        type="Conservative",
        max_drawdown=-0.08,
        position_limit=0.05
    )
```

### Async Tests

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None
```

---

## Coverage Requirements

**Minimum coverage by component**:
- Core services (Market Regime, AI Analysis): 80%
- Supporting services (Executor, Portfolio): 70%
- Utilities (shared/utils): 90%

**Check coverage**:
```bash
pytest --cov=src --cov-report=html
```

---

## CI/CD Testing

**GitHub Actions** (`.github/workflows/test.yml`):
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install pytest pytest-asyncio pytest-cov
          pip install -r requirements.txt
      - name: Run tests
        run: pytest --cov --cov-fail-under=80
```

---

## Test Data

**Location**: `tests/fixtures/`

```
tests/fixtures/
├── market_data.json        # Sample market data
├── regime_events.json      # Sample regime events
└── user_profiles.json      # Sample user profiles
```

**Usage**:
```python
import json

@pytest.fixture
def market_data():
    with open('tests/fixtures/market_data.json') as f:
        return json.load(f)
```

---

## Performance Testing

**Backtesting performance** (Phase 1, Task 10):
```python
import time

def test_backtesting_performance():
    start = time.time()
    result = backtest_strategy(data)
    duration = time.time() - start

    # VectorBT: 1000+ combinations in ~3s
    assert duration < 5.0
```

**gRPC latency** (Phase 1, Task 9):
```python
async def test_grpc_latency():
    start = time.time()
    result = await stub.GetStrategy(request)
    latency = (time.time() - start) * 1000  # ms

    # Target: < 50ms
    assert latency < 50
```

---

## Critical Testing Rules

1. **Never skip tests before commit**
2. **Mock all external APIs** (FinGPT, Claude, Alpha Vantage)
3. **Use docker-compose for integration tests** (start services automatically)
4. **Clean up test data after each test**
5. **Test error cases**, not just happy paths
