CREATE TABLE user_strategy_accounts (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  strategy TEXT NOT NULL CHECK (strategy IN ('managed', 'intelligent')),
  enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  initial_capital REAL NOT NULL DEFAULT 100000 CHECK (initial_capital > 0),
  cash_balance REAL NOT NULL DEFAULT 100000,
  open_margin REAL NOT NULL DEFAULT 100 CHECK (open_margin BETWEEN 10 AND 10000),
  open_leverage INTEGER NOT NULL DEFAULT 5 CHECK (open_leverage BETWEEN 1 AND 20),
  max_positions INTEGER NOT NULL DEFAULT 10 CHECK (max_positions BETWEEN 1 AND 50),
  allow_long INTEGER NOT NULL DEFAULT 1 CHECK (allow_long IN (0, 1)),
  allow_short INTEGER NOT NULL DEFAULT 1 CHECK (allow_short IN (0, 1)),
  strategy_params_json TEXT NOT NULL DEFAULT '{}',
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, strategy)
);

CREATE INDEX idx_user_strategy_accounts_enabled
  ON user_strategy_accounts (enabled, strategy, updated_at);

CREATE TABLE user_strategy_positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  strategy TEXT NOT NULL CHECK (strategy IN ('managed', 'intelligent')),
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('long', 'short')),
  leverage INTEGER NOT NULL,
  entry_price REAL NOT NULL CHECK (entry_price > 0),
  quantity REAL NOT NULL CHECK (quantity > 0),
  margin REAL NOT NULL CHECK (margin > 0),
  mark_price REAL NOT NULL CHECK (mark_price > 0),
  stop_price REAL,
  tp_price REAL,
  signal_json TEXT NOT NULL DEFAULT '{}',
  opened_at INTEGER NOT NULL,
  UNIQUE (user_id, strategy, symbol)
);

CREATE INDEX idx_user_strategy_positions_owner
  ON user_strategy_positions (user_id, strategy, opened_at DESC);

CREATE TABLE user_strategy_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  strategy TEXT NOT NULL CHECK (strategy IN ('managed', 'intelligent')),
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('long', 'short')),
  leverage INTEGER NOT NULL,
  entry_price REAL NOT NULL,
  exit_price REAL NOT NULL,
  quantity REAL NOT NULL,
  margin REAL NOT NULL,
  pnl_usdt REAL NOT NULL,
  pnl_pct REAL NOT NULL,
  close_reason TEXT NOT NULL,
  opened_at INTEGER NOT NULL,
  closed_at INTEGER NOT NULL
);

CREATE INDEX idx_user_strategy_trades_owner
  ON user_strategy_trades (user_id, strategy, closed_at DESC);
