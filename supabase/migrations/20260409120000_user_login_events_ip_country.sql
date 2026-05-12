-- Country/region label from IP geo lookup at login (e.g. China (CN)).
ALTER TABLE public.user_login_events
  ADD COLUMN IF NOT EXISTS ip_country TEXT;

COMMENT ON COLUMN public.user_login_events.ip_country IS
  'Country/region from IP geolocation at login; Local for private/loopback; null if lookup skipped/failed.';
