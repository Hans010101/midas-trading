ALTER TABLE market_overview_quotes
  RENAME TO market_overview_quotes_before_source_update;

CREATE TABLE market_overview_quotes (
  symbol TEXT PRIMARY KEY NOT NULL,
  market TEXT NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL CHECK (
    category IN ('index', 'commodity', 'forex', 'bond', 'sentiment', 'crypto')
  ),
  unit TEXT NOT NULL CHECK (
    unit IN ('point', 'price', 'rate', 'yield_pct')
  ),
  quoted_at INTEGER NOT NULL,
  last_point REAL NOT NULL CHECK (last_point > 0),
  prev_close REAL NOT NULL CHECK (prev_close >= 0),
  change_point REAL NOT NULL,
  change_pct REAL NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('yahoo', 'kraken')),
  updated_at INTEGER NOT NULL
);

INSERT INTO market_overview_quotes
  (symbol, market, name, category, unit, quoted_at, last_point, prev_close,
   change_point, change_pct, source, updated_at)
SELECT
  symbol, market, name, category, unit, quoted_at, last_point, prev_close,
  change_point, change_pct,
  CASE WHEN source = 'yahoo' THEN 'yahoo' ELSE 'kraken' END,
  updated_at
FROM market_overview_quotes_before_source_update;

DROP TABLE market_overview_quotes_before_source_update;

CREATE INDEX idx_market_overview_category
  ON market_overview_quotes (category, quoted_at DESC);
