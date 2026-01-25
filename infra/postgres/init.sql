-- BLOASIS Database Initialization
-- PostgreSQL + TimescaleDB setup
-- Note: Tables, hypertables, and indexes are managed by Alembic migrations

-- Enable TimescaleDB extension (cannot be done via Alembic)
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Create schemas (optional - can also be done via Alembic)
CREATE SCHEMA IF NOT EXISTS market_data;
CREATE SCHEMA IF NOT EXISTS trading;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA market_data IS 'Market data and price history';
COMMENT ON SCHEMA trading IS 'Trading operations and orders';
COMMENT ON SCHEMA analytics IS 'Analytics and backtesting results';
