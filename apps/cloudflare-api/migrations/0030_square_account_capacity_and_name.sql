UPDATE social_automation_accounts
SET daily_limit = 50,
    display_name = CASE
      WHEN account_key = 'legacy_midas' THEN '点金 Midas'
      ELSE display_name
    END,
    updated_at = CAST(strftime('%s', 'now') AS INTEGER) * 1000
WHERE account_key IN ('midas_trading', 'legacy_midas');
