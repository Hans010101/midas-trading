CREATE TABLE social_content_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  content_type TEXT NOT NULL
    CHECK (content_type IN ('news', 'whale', 'unlock')),
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  source_url TEXT NOT NULL,
  symbols_json TEXT NOT NULL DEFAULT '[]',
  score REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'drafted', 'ignored')),
  occurred_at INTEGER NOT NULL,
  ingested_at INTEGER NOT NULL,
  UNIQUE (source, source_id)
);

CREATE INDEX idx_social_content_events_queue
  ON social_content_events (status, score DESC, occurred_at DESC);

ALTER TABLE social_drafts ADD COLUMN content_type TEXT NOT NULL DEFAULT 'market_analysis'
  CHECK (content_type IN ('market_analysis', 'news', 'whale', 'unlock'));

ALTER TABLE social_drafts ADD COLUMN source_event_id INTEGER;

CREATE UNIQUE INDEX idx_social_drafts_source_event
  ON social_drafts (source_event_id)
  WHERE source_event_id IS NOT NULL;
