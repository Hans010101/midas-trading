ALTER TABLE social_drafts
  ADD COLUMN account_key TEXT NOT NULL DEFAULT 'midas_trading'
  CHECK (account_key IN ('midas_trading', 'legacy_midas'));

ALTER TABLE social_dispatches
  ADD COLUMN account_key TEXT NOT NULL DEFAULT 'midas_trading'
  CHECK (account_key IN ('midas_trading', 'legacy_midas'));

ALTER TABLE social_auto_runs
  ADD COLUMN account_key TEXT NOT NULL DEFAULT 'midas_trading'
  CHECK (account_key IN ('midas_trading', 'legacy_midas'));

CREATE INDEX idx_social_drafts_account_queue
  ON social_drafts (account_key, auto_drafted, created_at DESC);

CREATE INDEX idx_social_dispatches_account_status
  ON social_dispatches (account_key, platform, status, updated_at DESC);

CREATE TABLE social_automation_accounts (
  account_key TEXT PRIMARY KEY
    CHECK (account_key IN ('midas_trading', 'legacy_midas')),
  display_name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  circuit_open INTEGER NOT NULL DEFAULT 0 CHECK (circuit_open IN (0, 1)),
  platform_checked INTEGER NOT NULL DEFAULT 0 CHECK (platform_checked IN (0, 1)),
  daily_limit INTEGER NOT NULL DEFAULT 40 CHECK (daily_limit BETWEEN 1 AND 50),
  failure_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  content_profile TEXT NOT NULL
    CHECK (content_profile IN ('radar', 'legacy_market')),
  slot_offset_minutes INTEGER NOT NULL DEFAULT 0
    CHECK (slot_offset_minutes BETWEEN 0 AND 9),
  updated_at INTEGER NOT NULL
);

INSERT INTO social_automation_accounts
  (account_key, display_name, enabled, circuit_open, platform_checked,
   daily_limit, failure_count, last_error, content_profile,
   slot_offset_minutes, updated_at)
SELECT
  'midas_trading', '点金雷达', enabled, circuit_open, binance_checked,
  daily_limit, failure_count, last_error, 'radar', 0, updated_at
FROM social_automation_config
WHERE id = 1;

-- The legacy account is intentionally dormant until its independent API key
-- has been transferred and a one-post acceptance check has passed.
INSERT INTO social_automation_accounts
  (account_key, display_name, enabled, circuit_open, platform_checked,
   daily_limit, failure_count, last_error, content_profile,
   slot_offset_minutes, updated_at)
VALUES
  ('legacy_midas', '点金 Midas', 0, 0, 0, 40, 0,
   '等待迁入旧币安广场独立 API Key', 'legacy_market', 5,
   CAST(strftime('%s', 'now') AS INTEGER) * 1000);
