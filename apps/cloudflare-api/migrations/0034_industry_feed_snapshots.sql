CREATE TABLE industry_feed_snapshots (
  feed TEXT PRIMARY KEY,
  checked_at INTEGER NOT NULL,
  items_json TEXT NOT NULL
);
