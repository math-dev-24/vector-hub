ALTER TABLE documents ADD COLUMN version INTEGER NOT NULL DEFAULT 0;

ALTER TABLE chunks ADD COLUMN metadata_model TEXT;
ALTER TABLE chunks ADD COLUMN metadata_prompt_version TEXT;
ALTER TABLE chunks ADD COLUMN title_source TEXT NOT NULL DEFAULT 'automatic';
ALTER TABLE chunks ADD COLUMN summary_source TEXT NOT NULL DEFAULT 'automatic';
ALTER TABLE chunks ADD COLUMN category_source TEXT NOT NULL DEFAULT 'automatic';
ALTER TABLE chunks ADD COLUMN tags_source TEXT NOT NULL DEFAULT 'automatic';
ALTER TABLE chunks ADD COLUMN provenance_status TEXT NOT NULL DEFAULT 'exact';

CREATE TABLE chunk_embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO chunk_embeddings
    (chunk_id, model, input_hash, dimensions, embedding_json, created_at, updated_at)
SELECT id, 'legacy', COALESCE(embedded_content_hash, content_hash), 0,
       embedding_json, created_at, updated_at
FROM chunks
WHERE embedding_json IS NOT NULL;

CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES chunks(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE UNIQUE INDEX idx_pages_document_position_unique
    ON pages(document_id, position);
CREATE UNIQUE INDEX idx_pages_document_number_unique
    ON pages(document_id, page_number);
CREATE UNIQUE INDEX idx_chunks_document_position_unique
    ON chunks(document_id, position);
CREATE INDEX idx_jobs_status_created ON jobs(status, created_at);
