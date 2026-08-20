CREATE TABLE telegram_market_scan_states (
  symbol TEXT PRIMARY KEY NOT NULL,
  state TEXT NOT NULL,
  state_label TEXT NOT NULL,
  bias TEXT NOT NULL,
  pct_b REAL NOT NULL,
  zone_label TEXT NOT NULL,
  bandwidth REAL NOT NULL,
  close REAL NOT NULL,
  mid REAL NOT NULL,
  upper REAL NOT NULL,
  lower REAL NOT NULL,
  change_pct_24h REAL,
  funding_rate REAL,
  transition INTEGER NOT NULL DEFAULT 0 CHECK (transition IN (0, 1)),
  transition_from TEXT,
  last_transition_sent_at INTEGER,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_telegram_market_scan_updated
  ON telegram_market_scan_states (updated_at DESC);
