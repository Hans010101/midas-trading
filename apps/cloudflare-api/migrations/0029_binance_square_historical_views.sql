ALTER TABLE social_automation_accounts ADD COLUMN historical_view_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE social_automation_accounts ADD COLUMN historical_views_7d INTEGER NOT NULL DEFAULT 0;
ALTER TABLE social_automation_accounts ADD COLUMN historical_metrics_updated_at INTEGER;
