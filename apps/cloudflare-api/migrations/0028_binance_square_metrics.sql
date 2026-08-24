ALTER TABLE social_dispatches ADD COLUMN platform_post_id TEXT;
ALTER TABLE social_dispatches ADD COLUMN view_count INTEGER;
ALTER TABLE social_dispatches ADD COLUMN like_count INTEGER;
ALTER TABLE social_dispatches ADD COLUMN comment_count INTEGER;
ALTER TABLE social_dispatches ADD COLUMN share_count INTEGER;
ALTER TABLE social_dispatches ADD COLUMN metrics_updated_at INTEGER;

ALTER TABLE social_automation_accounts ADD COLUMN platform_user_id TEXT;
ALTER TABLE social_automation_accounts ADD COLUMN follower_count INTEGER;
ALTER TABLE social_automation_accounts ADD COLUMN follower_updated_at INTEGER;
