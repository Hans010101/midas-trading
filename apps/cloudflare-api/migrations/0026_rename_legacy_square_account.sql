UPDATE social_automation_accounts
SET display_name = '点金',
    updated_at = CAST(strftime('%s', 'now') AS INTEGER) * 1000
WHERE account_key = 'legacy_midas';
