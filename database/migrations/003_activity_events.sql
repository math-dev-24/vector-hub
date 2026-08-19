CREATE TABLE activity_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    document_id TEXT,
    chunk_id TEXT,
    job_id TEXT,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX idx_activity_events_created ON activity_events(created_at DESC);
CREATE INDEX idx_activity_events_document ON activity_events(document_id, created_at DESC);
