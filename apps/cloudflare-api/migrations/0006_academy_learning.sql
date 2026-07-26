ALTER TABLE users ADD COLUMN subscription_expires_at INTEGER;

CREATE TABLE academy_progress (
  user_id TEXT NOT NULL,
  article_slug TEXT NOT NULL,
  stage TEXT NOT NULL,
  completed_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, article_slug),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_academy_progress_user_stage
  ON academy_progress (user_id, stage);

CREATE TABLE academy_exam_results (
  id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  score INTEGER NOT NULL,
  total INTEGER NOT NULL,
  passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
  created_at INTEGER NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_academy_exam_results_user_stage
  ON academy_exam_results (user_id, stage, created_at DESC);

CREATE TABLE academy_exam_awards (
  id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  awarded_days INTEGER NOT NULL DEFAULT 7,
  awarded_at INTEGER NOT NULL,
  UNIQUE (user_id, stage),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_academy_exam_awards_awarded_at
  ON academy_exam_awards (awarded_at DESC);
