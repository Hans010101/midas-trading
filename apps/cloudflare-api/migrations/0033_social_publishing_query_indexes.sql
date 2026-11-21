CREATE INDEX IF NOT EXISTS idx_social_dispatches_pending_time
  ON social_dispatches(updated_at)
  WHERE platform='binance_square' AND status='pending';

CREATE INDEX IF NOT EXISTS idx_social_auto_runs_draft_account
  ON social_auto_runs(draft_id, account_key);

CREATE INDEX IF NOT EXISTS idx_social_dispatches_unmeasured
  ON social_dispatches(created_at DESC)
  WHERE platform='binance_square' AND status='success' AND metrics_updated_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_social_dispatches_measured
  ON social_dispatches(created_at DESC)
  WHERE platform='binance_square' AND status='success' AND metrics_updated_at IS NOT NULL;
