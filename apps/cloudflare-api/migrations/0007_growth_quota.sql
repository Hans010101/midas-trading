ALTER TABLE users ADD COLUMN invite_code TEXT;
ALTER TABLE users ADD COLUMN trial_granted_at INTEGER;

CREATE UNIQUE INDEX idx_users_invite_code
  ON users (invite_code)
  WHERE invite_code IS NOT NULL;

CREATE TABLE invitations (
  id TEXT PRIMARY KEY NOT NULL,
  inviter_id TEXT NOT NULL,
  invitee_id TEXT NOT NULL UNIQUE,
  code TEXT NOT NULL,
  rewarded_at INTEGER,
  reward_claim_id TEXT UNIQUE,
  created_at INTEGER NOT NULL,
  FOREIGN KEY (inviter_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (invitee_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_invitations_inviter
  ON invitations (inviter_id, created_at DESC);

CREATE TABLE quota_usage (
  user_id TEXT NOT NULL,
  feature TEXT NOT NULL CHECK (feature IN ('diagnose', 'backtest')),
  usage_month TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0 CHECK (used >= 0),
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, feature, usage_month),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_quota_usage_month
  ON quota_usage (usage_month, feature);
