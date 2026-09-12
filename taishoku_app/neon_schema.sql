CREATE TABLE IF NOT EXISTS taishoku_jobs (
  reference_id TEXT PRIMARY KEY,
  event_id TEXT,
  status TEXT,
  delivery_allowed BOOLEAN,
  automatic_delivery BOOLEAN NOT NULL DEFAULT FALSE,
  manifest JSONB,
  normalized_answer JSONB,
  evaluation JSONB,
  source_payload JSONB,
  persisted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS taishoku_artifacts (
  reference_id TEXT NOT NULL REFERENCES taishoku_jobs(reference_id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  content_type TEXT NOT NULL,
  content BYTEA NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  persisted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (reference_id, file_name)
);

CREATE INDEX IF NOT EXISTS taishoku_jobs_event_id_idx ON taishoku_jobs(event_id);
