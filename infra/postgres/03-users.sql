-- BLOASIS User Data Schema
-- User accounts and trading preferences
-- Executed after init.sql

-- Create user_data schema
CREATE SCHEMA IF NOT EXISTS user_data;

COMMENT ON SCHEMA user_data IS 'User accounts and preferences';

-- Users table
CREATE TABLE user_data.users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE user_data.users IS 'User accounts';
COMMENT ON COLUMN user_data.users.user_id IS 'Unique user identifier (UUID)';
COMMENT ON COLUMN user_data.users.email IS 'Unique email address for login';
COMMENT ON COLUMN user_data.users.password_hash IS 'bcrypt hashed password';
COMMENT ON COLUMN user_data.users.name IS 'Display name';

-- User preferences table
CREATE TABLE user_data.user_preferences (
    user_id UUID PRIMARY KEY REFERENCES user_data.users(user_id) ON DELETE CASCADE,
    risk_profile VARCHAR(50) DEFAULT 'moderate' CHECK (risk_profile IN ('conservative', 'moderate', 'aggressive')),
    max_portfolio_risk DECIMAL(5,4) DEFAULT 0.20 CHECK (max_portfolio_risk BETWEEN 0 AND 1),
    max_position_size DECIMAL(5,4) DEFAULT 0.10 CHECK (max_position_size BETWEEN 0 AND 1),
    preferred_sectors TEXT[] DEFAULT '{}',
    enable_notifications BOOLEAN DEFAULT true,
    trading_enabled BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE user_data.user_preferences IS 'User trading preferences';
COMMENT ON COLUMN user_data.user_preferences.risk_profile IS 'Risk tolerance: conservative, moderate, aggressive';
COMMENT ON COLUMN user_data.user_preferences.max_portfolio_risk IS 'Maximum portfolio risk as decimal (0-1)';
COMMENT ON COLUMN user_data.user_preferences.max_position_size IS 'Maximum single position size as decimal (0-1)';
COMMENT ON COLUMN user_data.user_preferences.preferred_sectors IS 'Preferred trading sectors';
COMMENT ON COLUMN user_data.user_preferences.enable_notifications IS 'Whether to receive trading notifications';
COMMENT ON COLUMN user_data.user_preferences.trading_enabled IS 'AI 자동 거래 활성화 여부';

-- Indexes
CREATE INDEX idx_users_email ON user_data.users(email);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION user_data.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON user_data.users
    FOR EACH ROW
    EXECUTE FUNCTION user_data.update_updated_at_column();

CREATE TRIGGER update_user_preferences_updated_at
    BEFORE UPDATE ON user_data.user_preferences
    FOR EACH ROW
    EXECUTE FUNCTION user_data.update_updated_at_column();
