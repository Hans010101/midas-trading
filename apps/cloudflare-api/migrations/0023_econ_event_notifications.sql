-- Economic-calendar reminders are opt-out for registered users. Delivery is
-- deduplicated through in_app_notifications, so every event/user/lead-time is
-- emitted at most once even when the five-minute cron overlaps.

ALTER TABLE notification_configs ADD COLUMN econ_alert_enabled INTEGER NOT NULL DEFAULT 1
  CHECK (econ_alert_enabled IN (0, 1));

ALTER TABLE notification_configs ADD COLUMN econ_alert_minutes INTEGER NOT NULL DEFAULT 30
  CHECK (econ_alert_minutes IN (15, 30, 60));
