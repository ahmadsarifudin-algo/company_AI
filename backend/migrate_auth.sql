-- Fix users table: make hashed_password nullable, add invite columns
ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_token_hash VARCHAR(64);
ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_users_invite_token ON users (invite_token_hash);

-- Fix trace_index: add approval audit columns
ALTER TABLE trace_index ADD COLUMN IF NOT EXISTS approval_decision VARCHAR(20);
ALTER TABLE trace_index ADD COLUMN IF NOT EXISTS approved_by VARCHAR(100);
ALTER TABLE trace_index ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
