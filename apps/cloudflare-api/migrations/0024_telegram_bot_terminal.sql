CREATE TABLE telegram_bot_sessions (
  chat_id TEXT PRIMARY KEY NOT NULL,
  state_json TEXT NOT NULL DEFAULT '{}',
  state_expires_at INTEGER NOT NULL DEFAULT 0,
  command_window_started_at INTEGER NOT NULL DEFAULT 0,
  command_count INTEGER NOT NULL DEFAULT 0,
  order_window_started_at INTEGER NOT NULL DEFAULT 0,
  order_count INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL
);
