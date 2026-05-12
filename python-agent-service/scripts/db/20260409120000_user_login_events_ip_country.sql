-- Add ip_country to login audit (apply after user_login_events exists).
ALTER TABLE user_login_events
  ADD COLUMN IF NOT EXISTS ip_country TEXT;
