ALTER TABLE admin_action_logs RENAME TO admin_action_logs_before_operations;

CREATE TABLE admin_action_logs (
  id TEXT PRIMARY KEY NOT NULL,
  operator_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  target_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);

INSERT INTO admin_action_logs
  (id, operator_id, target_user_id, action, detail_json, created_at)
SELECT id, operator_id, target_user_id, action, detail_json, created_at
FROM admin_action_logs_before_operations;

DROP TABLE admin_action_logs_before_operations;

CREATE INDEX idx_admin_action_logs_target
  ON admin_action_logs (target_user_id, created_at DESC);

CREATE INDEX idx_admin_action_logs_operator
  ON admin_action_logs (operator_id, created_at DESC);

CREATE TABLE web_visit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  visitor_id TEXT NOT NULL,
  visit_date TEXT NOT NULL,
  visit_hour INTEGER NOT NULL CHECK (visit_hour BETWEEN 0 AND 23),
  source TEXT NOT NULL DEFAULT 'direct',
  referrer TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_web_visit_events_date
  ON web_visit_events (visit_date, visit_hour);

CREATE INDEX idx_web_visit_events_visitor
  ON web_visit_events (visitor_id, visit_date);

CREATE TABLE crawler_visit_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot TEXT NOT NULL,
  visit_date TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_crawler_visit_events_date
  ON crawler_visit_events (visit_date, bot);

CREATE TABLE weekly_dispatches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL,
  week INTEGER NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'uploaded'
    CHECK (status IN ('uploaded', 'scheduled', 'sent')),
  pdf_filename TEXT NOT NULL,
  md_content TEXT NOT NULL,
  extracted_json TEXT NOT NULL DEFAULT '{}',
  email_html TEXT NOT NULL,
  uploaded_at INTEGER NOT NULL,
  sent_at INTEGER,
  UNIQUE (year, week)
);

CREATE INDEX idx_weekly_dispatches_status
  ON weekly_dispatches (status, uploaded_at DESC);

CREATE TABLE weekly_dispatch_assets (
  dispatch_id INTEGER NOT NULL REFERENCES weekly_dispatches(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content BLOB NOT NULL,
  PRIMARY KEY (dispatch_id, chunk_index)
);

CREATE TABLE social_drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  bias TEXT NOT NULL,
  tweet_text TEXT NOT NULL,
  compliance_passed INTEGER NOT NULL DEFAULT 1
    CHECK (compliance_passed IN (0, 1)),
  compliance_reason TEXT,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'published', 'failed')),
  image_key TEXT,
  auto_drafted INTEGER NOT NULL DEFAULT 0
    CHECK (auto_drafted IN (0, 1)),
  has_url INTEGER NOT NULL DEFAULT 0
    CHECK (has_url IN (0, 1)),
  gen_style TEXT NOT NULL DEFAULT 'default'
    CHECK (gen_style IN ('default', 'x_short')),
  provider TEXT,
  model TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_social_drafts_created
  ON social_drafts (created_at DESC, gen_style);

CREATE TABLE social_dispatches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_id INTEGER NOT NULL REFERENCES social_drafts(id) ON DELETE CASCADE,
  platform TEXT NOT NULL CHECK (platform IN ('binance_square', 'x')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'success', 'failed')),
  url TEXT,
  error TEXT,
  source TEXT NOT NULL DEFAULT 'manual'
    CHECK (source IN ('manual', 'auto')),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  UNIQUE (draft_id, platform)
);

CREATE TABLE social_automation_config (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  circuit_open INTEGER NOT NULL DEFAULT 0 CHECK (circuit_open IN (0, 1)),
  binance_checked INTEGER NOT NULL DEFAULT 0 CHECK (binance_checked IN (0, 1)),
  x_checked INTEGER NOT NULL DEFAULT 0 CHECK (x_checked IN (0, 1)),
  daily_limit INTEGER NOT NULL DEFAULT 30 CHECK (daily_limit BETWEEN 1 AND 50),
  updated_at INTEGER NOT NULL
);

INSERT INTO social_automation_config
  (id, enabled, circuit_open, binance_checked, x_checked, daily_limit, updated_at)
VALUES (1, 0, 0, 0, 0, 30, 0);

CREATE TABLE virtual_strategy_accounts (
  strategy TEXT PRIMARY KEY CHECK (strategy IN ('managed', 'intelligent')),
  enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  initial_capital REAL NOT NULL DEFAULT 100000 CHECK (initial_capital > 0),
  cash_balance REAL NOT NULL DEFAULT 100000,
  open_margin REAL NOT NULL DEFAULT 100 CHECK (open_margin BETWEEN 10 AND 10000),
  open_leverage INTEGER NOT NULL DEFAULT 5 CHECK (open_leverage BETWEEN 1 AND 20),
  max_positions INTEGER NOT NULL DEFAULT 50 CHECK (max_positions BETWEEN 1 AND 200),
  allow_long INTEGER NOT NULL DEFAULT 1 CHECK (allow_long IN (0, 1)),
  allow_short INTEGER NOT NULL DEFAULT 1 CHECK (allow_short IN (0, 1)),
  exit_tp INTEGER NOT NULL DEFAULT 1 CHECK (exit_tp IN (0, 1)),
  exit_signal INTEGER NOT NULL DEFAULT 1 CHECK (exit_signal IN (0, 1)),
  exit_timeout INTEGER NOT NULL DEFAULT 1 CHECK (exit_timeout IN (0, 1)),
  tp_pct REAL NOT NULL DEFAULT 100 CHECK (tp_pct > 0),
  strategy_params_json TEXT NOT NULL DEFAULT '{}',
  updated_at INTEGER NOT NULL
);

INSERT INTO virtual_strategy_accounts
  (strategy, enabled, initial_capital, cash_balance, open_margin, open_leverage,
   max_positions, allow_long, allow_short, exit_tp, exit_signal, exit_timeout,
   tp_pct, strategy_params_json, updated_at)
VALUES
  ('managed', 0, 100000, 100000, 100, 5, 50, 1, 0, 1, 1, 1, 100, '{}', 0),
  (
    'intelligent', 0, 100000, 100000, 100, 5, 50, 1, 1, 1, 1, 1, 100,
    '{"threshold":3,"weights":{"boll":1,"macd":1,"ma":1,"rsi":1,"kdj":1,"extreme":1},"atr_stop_mult":2,"atr_tp_mult":4}',
    0
  );

CREATE TABLE virtual_strategy_positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy TEXT NOT NULL REFERENCES virtual_strategy_accounts(strategy),
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
  UNIQUE (strategy, symbol)
);

CREATE INDEX idx_virtual_strategy_positions_strategy
  ON virtual_strategy_positions (strategy, opened_at DESC);

CREATE TABLE virtual_strategy_trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  strategy TEXT NOT NULL REFERENCES virtual_strategy_accounts(strategy),
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

CREATE INDEX idx_virtual_strategy_trades_strategy
  ON virtual_strategy_trades (strategy, closed_at DESC);
