-- Cloud store is a sanitized projection, not a migration/deletion of local SQLite.
CREATE TABLE IF NOT EXISTS current_programmes (
  venue_id TEXT PRIMARY KEY,
  generation TEXT NOT NULL,
  checked_at TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS latest_attempts (
  venue_id TEXT PRIMARY KEY,
  generation TEXT NOT NULL,
  checked_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_history (
  venue_id TEXT NOT NULL,
  day TEXT NOT NULL,
  generation TEXT NOT NULL,
  payload TEXT NOT NULL,
  PRIMARY KEY (venue_id, day)
);
CREATE TABLE IF NOT EXISTS refresh_requests (
  id TEXT PRIMARY KEY, requested_at TEXT NOT NULL, state TEXT NOT NULL
);
