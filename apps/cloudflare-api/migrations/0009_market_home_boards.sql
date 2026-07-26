CREATE TABLE market_home_boards (
  market TEXT PRIMARY KEY NOT NULL CHECK (market IN ('cn', 'us', 'hk')),
  payload_json TEXT NOT NULL,
  quoted_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_market_home_boards_updated_at
  ON market_home_boards (updated_at DESC);
