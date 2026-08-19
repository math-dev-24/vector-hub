CREATE TABLE jobs_history_safe (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    document_id TEXT,
    chunk_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

INSERT INTO jobs_history_safe SELECT * FROM jobs;
DROP TABLE jobs;
ALTER TABLE jobs_history_safe RENAME TO jobs;
CREATE INDEX idx_jobs_status_created ON jobs(status, created_at);
