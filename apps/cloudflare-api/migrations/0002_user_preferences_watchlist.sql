PRAGMA foreign_keys = ON;

ALTER TABLE users
  ADD COLUMN avatar_id INTEGER CHECK (
    avatar_id IS NULL OR (avatar_id >= 1 AND avatar_id <= 16)
  );

ALTER TABLE users
  ADD COLUMN language_pref TEXT CHECK (
    language_pref IS NULL OR language_pref IN ('zh', 'en')
  );

ALTER TABLE users
  ADD COLUMN indicator_bollinger INTEGER NOT NULL DEFAULT 1 CHECK (
    indicator_bollinger IN (0, 1)
  );

ALTER TABLE users
  ADD COLUMN indicator_chan INTEGER NOT NULL DEFAULT 1 CHECK (
    indicator_chan IN (0, 1)
  );

ALTER TABLE users
  ADD COLUMN indicator_day_trade INTEGER NOT NULL DEFAULT 0 CHECK (
    indicator_day_trade IN (0, 1)
  );

ALTER TABLE users
  ADD COLUMN demo_watchlist_prefilled INTEGER NOT NULL DEFAULT 0 CHECK (
    demo_watchlist_prefilled IN (0, 1)
  );

CREATE TABLE watchlist_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL CHECK (market IN ('cn', 'us', 'hk', 'crypto')),
  sort_order INTEGER NOT NULL,
  added_at INTEGER NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE (user_id, symbol, market)
);

CREATE INDEX idx_watchlist_user_order
  ON watchlist_items (user_id, sort_order ASC, added_at ASC);
