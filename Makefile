.PHONY: help install lint fmt typecheck test test-cov clean db-init

help:
	@echo "BLOASIS Makefile"
	@echo ""
	@echo "  install      Install dependencies (dev extras)"
	@echo "  lint         Run ruff check"
	@echo "  fmt          Run ruff format"
	@echo "  typecheck    Run mypy strict"
	@echo "  test         Run pytest"
	@echo "  test-cov     Run pytest with coverage report"
	@echo "  db-init      Create SQLite database with tables"
	@echo "  clean        Remove caches and build artifacts"

install:
	uv sync --extra dev

lint:
	uv run ruff check bloasis/ tests/

fmt:
	uv run ruff format bloasis/ tests/

typecheck:
	uv run mypy bloasis/

test:
	uv run pytest tests/

test-cov:
	uv run pytest tests/ --cov=bloasis --cov-report=term-missing --cov-report=html

db-init:
	uv run bloasis init-db

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
