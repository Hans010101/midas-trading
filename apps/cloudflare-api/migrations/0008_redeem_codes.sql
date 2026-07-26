CREATE TABLE redeem_codes (
  id TEXT PRIMARY KEY NOT NULL,
  code TEXT NOT NULL UNIQUE,
  period TEXT NOT NULL CHECK (period IN ('month', 'quarter', 'year')),
  days INTEGER NOT NULL CHECK (days IN (30, 90, 365)),
  note TEXT,
  created_by TEXT,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  redeemed_by TEXT,
  redeemed_at INTEGER,
  redemption_claim_id TEXT UNIQUE,
  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
  FOREIGN KEY (redeemed_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_redeem_codes_created_at
  ON redeem_codes (created_at DESC);

CREATE INDEX idx_redeem_codes_expires_at
  ON redeem_codes (expires_at)
  WHERE redeemed_at IS NULL;
