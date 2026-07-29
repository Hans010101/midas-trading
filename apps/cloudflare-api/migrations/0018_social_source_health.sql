CREATE TABLE social_source_health (
  source TEXT PRIMARY KEY NOT NULL,
  status TEXT NOT NULL DEFAULT 'disabled'
    CHECK (status IN ('healthy', 'error', 'disabled')),
  last_attempt_at INTEGER NOT NULL,
  last_success_at INTEGER,
  last_error TEXT,
  last_inserted INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER NOT NULL DEFAULT 0
);
