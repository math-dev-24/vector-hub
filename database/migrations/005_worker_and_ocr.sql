ALTER TABLE pages ADD COLUMN extraction_method TEXT NOT NULL DEFAULT 'text_layer';
ALTER TABLE pages ADD COLUMN ocr_status TEXT NOT NULL DEFAULT 'not_needed';

ALTER TABLE jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN worker_id TEXT;
ALTER TABLE jobs ADD COLUMN api_calls INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0;

CREATE INDEX idx_jobs_claim ON jobs(status, cancel_requested, created_at);
