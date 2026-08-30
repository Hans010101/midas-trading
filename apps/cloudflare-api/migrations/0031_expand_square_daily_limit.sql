CREATE TABLE social_automation_accounts_new (
  account_key TEXT PRIMARY KEY
    CHECK (account_key IN ('midas_trading', 'legacy_midas')),
  display_name TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  circuit_open INTEGER NOT NULL DEFAULT 0 CHECK (circuit_open IN (0, 1)),
  platform_checked INTEGER NOT NULL DEFAULT 0 CHECK (platform_checked IN (0, 1)),
  daily_limit INTEGER NOT NULL DEFAULT 50 CHECK (daily_limit BETWEEN 1 AND 100),
  failure_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  content_profile TEXT NOT NULL
    CHECK (content_profile IN ('radar', 'legacy_market')),
  slot_offset_minutes INTEGER NOT NULL DEFAULT 0
    CHECK (slot_offset_minutes BETWEEN 0 AND 9),
  updated_at INTEGER NOT NULL,
  platform_user_id TEXT,
  follower_count INTEGER,
  follower_updated_at INTEGER,
  historical_view_count INTEGER NOT NULL DEFAULT 0,
  historical_views_7d INTEGER NOT NULL DEFAULT 0,
  historical_metrics_updated_at INTEGER
);

INSERT INTO social_automation_accounts_new (
  account_key, display_name, enabled, circuit_open, platform_checked,
  daily_limit, failure_count, last_error, content_profile,
  slot_offset_minutes, updated_at, platform_user_id, follower_count,
  follower_updated_at, historical_view_count, historical_views_7d,
  historical_metrics_updated_at
)
SELECT
  account_key, display_name, enabled, circuit_open, platform_checked,
  daily_limit, failure_count, last_error, content_profile,
  slot_offset_minutes, updated_at, platform_user_id, follower_count,
  follower_updated_at, historical_view_count, historical_views_7d,
  historical_metrics_updated_at
FROM social_automation_accounts;

DROP TABLE social_automation_accounts;
ALTER TABLE social_automation_accounts_new RENAME TO social_automation_accounts;
