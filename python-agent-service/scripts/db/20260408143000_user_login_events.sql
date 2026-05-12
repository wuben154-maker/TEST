-- Login history for account settings. Apply to existing local DBs after init_local_db.sql.

CREATE TABLE IF NOT EXISTS user_login_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
  logged_in_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip_address TEXT,
  user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_login_events_user_logged_in
  ON user_login_events (user_id, logged_in_at DESC);
