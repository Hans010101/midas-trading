CREATE TABLE notification_configs (
  user_id TEXT PRIMARY KEY NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tg_chat_id TEXT,
  feishu_open_id TEXT,
  trade_alert_enabled INTEGER NOT NULL DEFAULT 1 CHECK (trade_alert_enabled IN (0, 1)),
  price_alert_enabled INTEGER NOT NULL DEFAULT 1 CHECK (price_alert_enabled IN (0, 1)),
  weekly_report_enabled INTEGER NOT NULL DEFAULT 0 CHECK (weekly_report_enabled IN (0, 1)),
  dott_digest_enabled INTEGER NOT NULL DEFAULT 0 CHECK (dott_digest_enabled IN (0, 1)),
  dott_transition_enabled INTEGER NOT NULL DEFAULT 0 CHECK (dott_transition_enabled IN (0, 1)),
  quiet_hours_enabled INTEGER NOT NULL DEFAULT 0 CHECK (quiet_hours_enabled IN (0, 1)),
  quiet_hours_start INTEGER NOT NULL DEFAULT 23 CHECK (quiet_hours_start BETWEEN 0 AND 23),
  quiet_hours_end INTEGER NOT NULL DEFAULT 7 CHECK (quiet_hours_end BETWEEN 0 AND 23),
  quiet_hours_tz TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE notification_bind_tokens (
  token_hash TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  channel TEXT NOT NULL CHECK (channel IN ('telegram', 'feishu')),
  expires_at INTEGER NOT NULL,
  used_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_notification_bind_tokens_expiry
  ON notification_bind_tokens (expires_at);

CREATE TABLE alert_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  market TEXT NOT NULL CHECK (market IN ('cn', 'us', 'hk', 'crypto')),
  symbol TEXT,
  indicator TEXT NOT NULL,
  operator TEXT NOT NULL CHECK (operator IN ('gt', 'gte', 'lt', 'lte')),
  threshold TEXT NOT NULL,
  timeframe TEXT,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  cooldown_sec INTEGER NOT NULL DEFAULT 300 CHECK (cooldown_sec BETWEEN 60 AND 86400),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_alert_rules_user ON alert_rules (user_id, created_at);

CREATE TABLE in_app_notifications (
  id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  read_at INTEGER,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_in_app_notifications_user
  ON in_app_notifications (user_id, created_at DESC);
