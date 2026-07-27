CREATE TABLE bot_order_presets (
  user_id TEXT PRIMARY KEY NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  perp_leverage INTEGER NOT NULL DEFAULT 3 CHECK (perp_leverage BETWEEN 1 AND 20),
  perp_notional_usdt TEXT NOT NULL DEFAULT '100',
  perp_margin_mode TEXT NOT NULL DEFAULT 'isolated'
    CHECK (perp_margin_mode IN ('isolated', 'cross')),
  spot_notional_cny TEXT NOT NULL DEFAULT '10000',
  spot_notional_usd TEXT NOT NULL DEFAULT '1000',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE support_tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  contact_email TEXT NOT NULL,
  category TEXT NOT NULL
    CHECK (category IN ('not_received', 'duplicate_charge', 'activation_failed', 'other')),
  description TEXT NOT NULL,
  related_order_id TEXT,
  image_count INTEGER NOT NULL DEFAULT 0 CHECK (image_count BETWEEN 0 AND 3),
  status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'resolved', 'closed')),
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_support_tickets_user_created
  ON support_tickets (user_id, created_at DESC);
