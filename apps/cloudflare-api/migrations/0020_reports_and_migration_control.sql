CREATE TABLE market_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'approved', 'sent', 'failed')),
  period_start TEXT,
  period_end TEXT,
  provider TEXT,
  model TEXT,
  approved_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  approved_at INTEGER,
  sent_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_market_reports_status
  ON market_reports (status, created_at DESC);

CREATE TABLE report_materials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL CHECK (content_type IN ('md', 'txt', 'pdf')),
  size INTEGER NOT NULL,
  char_count INTEGER NOT NULL,
  extracted_text TEXT NOT NULL DEFAULT '',
  period_start TEXT,
  period_end TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_report_materials_period
  ON report_materials (period_start, period_end, created_at DESC);

ALTER TABLE legacy_migration_runs ADD COLUMN operator_id TEXT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE legacy_migration_runs ADD COLUMN dry_run INTEGER NOT NULL DEFAULT 1 CHECK (dry_run IN (0, 1));
