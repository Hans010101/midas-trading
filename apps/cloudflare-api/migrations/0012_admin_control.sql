ALTER TABLE users ADD COLUMN banned_at INTEGER;

CREATE TABLE admin_action_logs (
  id TEXT PRIMARY KEY NOT NULL,
  operator_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  target_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL CHECK (
    action IN (
      'user.banned',
      'user.unbanned',
      'user.sessions_revoked',
      'support.status_updated'
    )
  ),
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_admin_action_logs_target
  ON admin_action_logs (target_user_id, created_at DESC);

CREATE INDEX idx_admin_action_logs_operator
  ON admin_action_logs (operator_id, created_at DESC);

UPDATE users
SET role = 'admin', banned_at = NULL,
    updated_at = CAST(strftime('%s', 'now') AS INTEGER) * 1000
WHERE LOWER(email) IN (
  'hans.pan.007@gmail.com',
  'hans.pan007@gmail.com'
) OR (
  REPLACE(SUBSTR(LOWER(email), 1, INSTR(email, '@') - 1), '.', '') = 'hanspan007'
  AND SUBSTR(LOWER(email), INSTR(email, '@') + 1) IN ('gmail.com', 'googlemail.com')
);

CREATE TRIGGER lock_owner_admin_after_insert
AFTER INSERT ON users
WHEN
  REPLACE(SUBSTR(LOWER(NEW.email), 1, INSTR(NEW.email, '@') - 1), '.', '') = 'hanspan007'
  AND SUBSTR(LOWER(NEW.email), INSTR(NEW.email, '@') + 1) IN ('gmail.com', 'googlemail.com')
BEGIN
  UPDATE users
  SET role = 'admin', banned_at = NULL
  WHERE id = NEW.id;
END;

CREATE TRIGGER prevent_owner_admin_demotion
BEFORE UPDATE OF role ON users
WHEN
  REPLACE(SUBSTR(LOWER(OLD.email), 1, INSTR(OLD.email, '@') - 1), '.', '') = 'hanspan007'
  AND SUBSTR(LOWER(OLD.email), INSTR(OLD.email, '@') + 1) IN ('gmail.com', 'googlemail.com')
  AND NEW.role <> 'admin'
BEGIN
  SELECT RAISE(ABORT, 'locked administrator cannot be demoted');
END;

CREATE TRIGGER prevent_owner_admin_ban
BEFORE UPDATE OF banned_at ON users
WHEN
  REPLACE(SUBSTR(LOWER(OLD.email), 1, INSTR(OLD.email, '@') - 1), '.', '') = 'hanspan007'
  AND SUBSTR(LOWER(OLD.email), INSTR(OLD.email, '@') + 1) IN ('gmail.com', 'googlemail.com')
  AND NEW.banned_at IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'locked administrator cannot be banned');
END;

CREATE TRIGGER prevent_owner_admin_delete
BEFORE DELETE ON users
WHEN
  REPLACE(SUBSTR(LOWER(OLD.email), 1, INSTR(OLD.email, '@') - 1), '.', '') = 'hanspan007'
  AND SUBSTR(LOWER(OLD.email), INSTR(OLD.email, '@') + 1) IN ('gmail.com', 'googlemail.com')
BEGIN
  SELECT RAISE(ABORT, 'locked administrator cannot be deleted');
END;
