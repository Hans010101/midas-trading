ALTER TABLE users ADD COLUMN phone_e164 TEXT;
ALTER TABLE users ADD COLUMN phone_verified_at INTEGER;

CREATE UNIQUE INDEX idx_users_phone_e164
  ON users (phone_e164)
  WHERE phone_e164 IS NOT NULL;

CREATE TABLE sms_challenges (
  id TEXT PRIMARY KEY NOT NULL,
  phone_e164 TEXT NOT NULL,
  ip_hash TEXT,
  expires_at INTEGER NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  consumed_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_sms_challenges_phone_created
  ON sms_challenges (phone_e164, created_at DESC);

CREATE INDEX idx_sms_challenges_ip_created
  ON sms_challenges (ip_hash, created_at DESC)
  WHERE ip_hash IS NOT NULL;
