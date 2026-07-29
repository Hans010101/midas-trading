UPDATE social_automation_config
SET daily_limit = 40,
    updated_at = CAST(strftime('%s', 'now') AS INTEGER) * 1000
WHERE id = 1;
