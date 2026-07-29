ALTER TABLE social_automation_config
  ADD COLUMN failure_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE social_automation_config
  ADD COLUMN last_error TEXT;

CREATE TABLE social_auto_runs (
  slot TEXT PRIMARY KEY,
  status TEXT NOT NULL
    CHECK (status IN ('running', 'success', 'failed', 'skipped')),
  draft_id INTEGER REFERENCES social_drafts(id) ON DELETE SET NULL,
  dispatch_id INTEGER REFERENCES social_dispatches(id) ON DELETE SET NULL,
  error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_social_auto_runs_created
  ON social_auto_runs (created_at DESC);
