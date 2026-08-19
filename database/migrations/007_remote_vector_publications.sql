CREATE TABLE remote_vector_publications (
    chunk_id TEXT NOT NULL,
    destination TEXT NOT NULL,
    remote_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'published',
    error_message TEXT,
    published_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (chunk_id, destination),
    FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);

CREATE INDEX idx_remote_vector_publications_status
    ON remote_vector_publications(destination, status);
