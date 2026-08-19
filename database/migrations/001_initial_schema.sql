CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    original_path TEXT NOT NULL DEFAULT '',
    pages_status TEXT NOT NULL DEFAULT 'draft',
    chunks_status TEXT NOT NULL DEFAULT 'missing',
    vector_status TEXT NOT NULL DEFAULT 'missing',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    position INTEGER NOT NULL,
    original_text TEXT NOT NULL,
    corrected_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok'
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    text TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    keywords_json TEXT NOT NULL DEFAULT '[]',
    section_path_json TEXT NOT NULL DEFAULT '[]',
    sources_json TEXT NOT NULL DEFAULT '[]',
    token_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    metadata_status TEXT NOT NULL DEFAULT 'pending',
    manually_reviewed INTEGER NOT NULL DEFAULT 0,
    embedding_status TEXT NOT NULL DEFAULT 'missing',
    embedded_content_hash TEXT,
    embedding_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pages_document_position
    ON pages(document_id, position);
CREATE INDEX IF NOT EXISTS idx_chunks_document_position
    ON chunks(document_id, position);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_status
    ON chunks(embedding_status);
