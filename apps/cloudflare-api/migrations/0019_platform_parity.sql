-- Independent platform parity foundation.
-- Keeps legacy identifiers only as import references; the Cloudflare user id
-- remains the authoritative primary key after cutover.

ALTER TABLE users ADD COLUMN legacy_user_id TEXT;
CREATE UNIQUE INDEX idx_users_legacy_user_id
  ON users (legacy_user_id)
  WHERE legacy_user_id IS NOT NULL;

CREATE TABLE econ_events (
  event_key TEXT PRIMARY KEY NOT NULL,
  event_type TEXT NOT NULL,
  title_zh TEXT NOT NULL,
  title_en TEXT NOT NULL,
  markets_json TEXT NOT NULL DEFAULT '[]',
  importance INTEGER NOT NULL CHECK (importance BETWEEN 1 AND 3),
  scheduled_at INTEGER NOT NULL,
  time_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (time_confirmed IN (0, 1)),
  source TEXT NOT NULL,
  source_url TEXT,
  payload_hash TEXT,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_econ_events_scheduled
  ON econ_events (scheduled_at, importance DESC);

CREATE TABLE alert_rule_states (
  rule_id INTEGER PRIMARY KEY NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
  last_value REAL,
  last_condition_met INTEGER NOT NULL DEFAULT 0 CHECK (last_condition_met IN (0, 1)),
  last_evaluated_at INTEGER,
  last_triggered_at INTEGER,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  updated_at INTEGER NOT NULL
);

CREATE TABLE notification_deliveries (
  id TEXT PRIMARY KEY NOT NULL,
  notification_id TEXT NOT NULL REFERENCES in_app_notifications(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  channel TEXT NOT NULL CHECK (channel IN ('in_app', 'telegram', 'feishu')),
  status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed', 'skipped')),
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  sent_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE (notification_id, channel)
);

CREATE INDEX idx_notification_deliveries_status
  ON notification_deliveries (status, updated_at);

CREATE TABLE virtual_accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  legacy_id TEXT,
  market TEXT NOT NULL CHECK (market IN ('cn', 'us', 'hk', 'crypto')),
  currency TEXT NOT NULL CHECK (currency IN ('CNY', 'USD', 'HKD', 'USDT')),
  initial_capital REAL NOT NULL CHECK (initial_capital > 0),
  cash_balance REAL NOT NULL,
  realized_pnl REAL NOT NULL DEFAULT 0,
  activated_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE (user_id, market)
);

CREATE UNIQUE INDEX idx_virtual_accounts_legacy
  ON virtual_accounts (legacy_id)
  WHERE legacy_id IS NOT NULL;

CREATE TABLE virtual_positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES virtual_accounts(id) ON DELETE CASCADE,
  legacy_id TEXT,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  position_side TEXT NOT NULL DEFAULT 'long' CHECK (position_side IN ('long', 'short')),
  quantity REAL NOT NULL CHECK (quantity >= 0),
  avg_entry_price REAL NOT NULL CHECK (avg_entry_price > 0),
  realized_pnl REAL NOT NULL DEFAULT 0,
  opened_at INTEGER NOT NULL,
  closed_at INTEGER
);

CREATE UNIQUE INDEX idx_virtual_positions_active
  ON virtual_positions (account_id, symbol, position_side)
  WHERE closed_at IS NULL;

CREATE TABLE virtual_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES virtual_accounts(id) ON DELETE CASCADE,
  legacy_id TEXT,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
  position_side TEXT NOT NULL DEFAULT 'long' CHECK (position_side IN ('long', 'short')),
  order_type TEXT NOT NULL DEFAULT 'market' CHECK (order_type = 'market'),
  quantity REAL NOT NULL,
  price REAL,
  notional REAL,
  commission REAL,
  slippage_cost REAL,
  realized_pnl REAL,
  status TEXT NOT NULL CHECK (status IN ('filled', 'rejected')),
  reject_reason TEXT,
  source TEXT NOT NULL DEFAULT 'manual',
  placed_at INTEGER NOT NULL,
  filled_at INTEGER
);

CREATE INDEX idx_virtual_orders_account
  ON virtual_orders (account_id, placed_at DESC);

CREATE TABLE virtual_equity_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES virtual_accounts(id) ON DELETE CASCADE,
  market TEXT NOT NULL,
  cash REAL NOT NULL,
  positions_value REAL NOT NULL,
  equity REAL NOT NULL,
  realized_pnl_cumulative REAL NOT NULL,
  trigger_kind TEXT NOT NULL CHECK (trigger_kind IN ('order_filled', 'daily', 'migration')),
  snapshot_at INTEGER NOT NULL
);

CREATE INDEX idx_virtual_equity_account
  ON virtual_equity_snapshots (account_id, snapshot_at);

CREATE TABLE virtual_perp_positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES virtual_accounts(id) ON DELETE CASCADE,
  legacy_id TEXT,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('long', 'short')),
  margin_mode TEXT NOT NULL DEFAULT 'isolated' CHECK (margin_mode IN ('isolated', 'cross')),
  leverage INTEGER NOT NULL CHECK (leverage BETWEEN 1 AND 20),
  quantity REAL NOT NULL CHECK (quantity > 0),
  entry_price REAL NOT NULL CHECK (entry_price > 0),
  initial_margin REAL NOT NULL CHECK (initial_margin > 0),
  maintenance_margin_rate REAL NOT NULL DEFAULT 0.005,
  liquidation_price REAL NOT NULL,
  realized_pnl REAL NOT NULL DEFAULT 0,
  fee_paid REAL NOT NULL DEFAULT 0,
  funding_paid REAL NOT NULL DEFAULT 0,
  opened_at INTEGER NOT NULL,
  closed_at INTEGER,
  close_reason TEXT CHECK (close_reason IS NULL OR close_reason IN ('manual', 'liquidated', 'reset'))
);

CREATE UNIQUE INDEX idx_virtual_perp_positions_active
  ON virtual_perp_positions (account_id, symbol)
  WHERE closed_at IS NULL;

CREATE INDEX idx_virtual_perp_positions_scan
  ON virtual_perp_positions (closed_at, symbol);

CREATE TABLE virtual_perp_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES virtual_accounts(id) ON DELETE CASCADE,
  position_id INTEGER REFERENCES virtual_perp_positions(id) ON DELETE SET NULL,
  legacy_id TEXT,
  symbol TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('open_long', 'open_short', 'close_long', 'close_short')),
  leverage INTEGER,
  quantity REAL NOT NULL,
  price REAL,
  notional REAL,
  margin_delta REAL,
  fee REAL,
  realized_pnl REAL,
  status TEXT NOT NULL CHECK (status IN ('filled', 'rejected')),
  reject_reason TEXT,
  is_liquidation INTEGER NOT NULL DEFAULT 0 CHECK (is_liquidation IN (0, 1)),
  placed_at INTEGER NOT NULL,
  filled_at INTEGER
);

CREATE INDEX idx_virtual_perp_orders_account
  ON virtual_perp_orders (account_id, placed_at DESC);

CREATE TABLE virtual_perp_funding (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES virtual_accounts(id) ON DELETE CASCADE,
  position_id INTEGER NOT NULL REFERENCES virtual_perp_positions(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('long', 'short')),
  funding_rate REAL NOT NULL,
  mark_price REAL NOT NULL,
  quantity REAL NOT NULL,
  payment REAL NOT NULL,
  funding_ts INTEGER NOT NULL,
  settled_at INTEGER NOT NULL,
  UNIQUE (position_id, funding_ts)
);

CREATE TABLE conditional_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  legacy_id TEXT,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL CHECK (market IN ('cn', 'us', 'hk', 'crypto')),
  order_kind TEXT NOT NULL CHECK (order_kind IN ('limit', 'stop_loss', 'take_profit')),
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
  position_side TEXT NOT NULL DEFAULT 'long' CHECK (position_side IN ('long', 'short')),
  trigger_price REAL NOT NULL CHECK (trigger_price > 0),
  quantity REAL,
  leverage INTEGER,
  margin REAL,
  margin_mode TEXT CHECK (margin_mode IS NULL OR margin_mode IN ('isolated', 'cross')),
  expires_at INTEGER,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'triggered', 'cancelled', 'expired', 'failed')),
  triggered_order_id INTEGER,
  note TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_conditional_orders_scan
  ON conditional_orders (status, market, created_at);
CREATE INDEX idx_conditional_orders_user
  ON conditional_orders (user_id, created_at DESC);

CREATE TABLE backtest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  legacy_id TEXT,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT 'crypto',
  period TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  params_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'error')),
  metrics_json TEXT,
  equity_json TEXT,
  trades_json TEXT,
  run_card_json TEXT,
  error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX idx_backtest_runs_user
  ON backtest_runs (user_id, created_at DESC);

CREATE TABLE legacy_migration_runs (
  id TEXT PRIMARY KEY NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('planned', 'running', 'verified', 'failed', 'rolled_back')),
  source_revision TEXT,
  source_counts_json TEXT NOT NULL DEFAULT '{}',
  imported_counts_json TEXT NOT NULL DEFAULT '{}',
  checksum_json TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  started_at INTEGER,
  completed_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE legacy_user_mappings (
  legacy_user_id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  email TEXT NOT NULL COLLATE NOCASE,
  source_updated_at INTEGER,
  migrated_at INTEGER NOT NULL
);
