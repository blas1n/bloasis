-- BLOASIS Broker Configuration
-- Global broker settings (Phase 1: single Alpaca account)
-- Values are Fernet-encrypted at the application layer

CREATE TABLE IF NOT EXISTS user_data.broker_config (
    config_key VARCHAR(100) PRIMARY KEY,
    encrypted_value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE user_data.broker_config IS 'Global broker configuration (encrypted key-value)';
COMMENT ON COLUMN user_data.broker_config.config_key IS 'Configuration key (e.g., alpaca_api_key)';
COMMENT ON COLUMN user_data.broker_config.encrypted_value IS 'Fernet-encrypted configuration value';

-- Reuse the existing trigger function from 03-users.sql
CREATE TRIGGER update_broker_config_updated_at
    BEFORE UPDATE ON user_data.broker_config
    FOR EACH ROW
    EXECUTE FUNCTION user_data.update_updated_at_column();
