from __future__ import annotations

from models.document_model import utc_now
from repositories.sqlite_document_repository import SQLiteDocumentRepository


class SQLiteRemotePublicationRepository:
    def __init__(self, database_path):
        self.database = SQLiteDocumentRepository(database_path)

    def mark_published(self, chunk_id: str, destination: str, input_hash: str) -> None:
        now = utc_now().isoformat()
        with self.database._connect() as connection:
            connection.execute("""INSERT INTO remote_vector_publications
                (chunk_id, destination, remote_id, input_hash, status, error_message,
                 published_at, updated_at) VALUES (?, ?, ?, ?, 'published', NULL, ?, ?)
                ON CONFLICT(chunk_id, destination) DO UPDATE SET
                remote_id=excluded.remote_id, input_hash=excluded.input_hash,
                status='published', error_message=NULL,
                published_at=excluded.published_at, updated_at=excluded.updated_at""",
                (chunk_id, destination, chunk_id, input_hash, now, now))

    def mark_error(self, chunk_id: str, destination: str, input_hash: str,
                   message: str) -> None:
        now = utc_now().isoformat()
        with self.database._connect() as connection:
            connection.execute("""INSERT INTO remote_vector_publications
                (chunk_id, destination, remote_id, input_hash, status, error_message, updated_at)
                VALUES (?, ?, ?, ?, 'error', ?, ?)
                ON CONFLICT(chunk_id, destination) DO UPDATE SET
                input_hash=excluded.input_hash, status='error',
                error_message=excluded.error_message, updated_at=excluded.updated_at""",
                (chunk_id, destination, chunk_id, input_hash, message[:500], now))

    def get_input_hash(self, chunk_id: str, destination: str) -> str | None:
        with self.database._connect() as connection:
            row = connection.execute("""SELECT input_hash FROM remote_vector_publications
                WHERE chunk_id=? AND destination=? AND status='published'""",
                (chunk_id, destination)).fetchone()
        return row["input_hash"] if row else None

    def summary(self, document_id: str, destination: str) -> dict[str, int]:
        with self.database._connect() as connection:
            rows = connection.execute("""SELECT e.input_hash AS current_hash,
                       p.input_hash AS published_hash, p.status, c.embedding_status
                FROM chunks c
                LEFT JOIN chunk_embeddings e ON e.chunk_id=c.id
                LEFT JOIN remote_vector_publications p
                  ON p.chunk_id=c.id AND p.destination=?
                WHERE c.document_id=?""", (destination, document_id)).fetchall()
        result = {"published": 0, "outdated": 0, "missing": 0, "error": 0}
        for row in rows:
            if row["status"] == "error":
                result["error"] += 1
            elif (row["embedding_status"] == "ready" and row["published_hash"]
                  and row["published_hash"] == row["current_hash"]):
                result["published"] += 1
            elif row["published_hash"]:
                result["outdated"] += 1
            else:
                result["missing"] += 1
        return result
