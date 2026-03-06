---
description: Testing rules and coverage requirements
---

# Testing Rules

## CRITICAL: Tests Are Mandatory

**NEVER commit code without tests.**

**Minimum coverage: 80%**

### Test Organization

```
app/
├── core/tests/           # Pure function unit tests
│   ├── test_risk_rules.py
│   ├── test_signal_generator.py
│   ├── test_factor_scoring.py
│   ├── test_regime_classifier.py
│   └── test_prompts.py
├── services/tests/       # Service layer tests (mock I/O)
│   ├── test_user_service.py
│   ├── test_portfolio_service.py
│   ├── test_executor_service.py
│   └── test_strategy_service.py
└── routers/tests/        # API endpoint tests (TestClient)
    ├── test_auth.py
    └── test_orders.py
```

### Mock External APIs

**ALWAYS mock**: Claude API, yfinance, Alpaca API, database connections (in unit tests).

**NEVER call real APIs in tests.**

### Running Tests

```bash
# Full test suite with coverage
pytest app/ --cov=app --cov-fail-under=80

# Specific module
pytest app/core/tests/ -v

# Lint
ruff check app/ shared/
```

### Code Quality

```bash
ruff check app/ shared/
ruff format --check app/ shared/
```
