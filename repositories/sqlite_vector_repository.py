from __future__ import annotations

import json
import math

from models.document_model import utc_now
from repositories.sqlite_document_repository import SQLiteDocumentRepository


class SQLiteVectorRepository:
    def __init__(self, database_path):
        self.database = SQLiteDocumentRepository(database_path)

    def exists(self, chunk_id: str) -> bool:
        with self.database._connect() as connection:
            return connection.execute(
                "SELECT 1 FROM chunk_embeddings WHERE chunk_id=?", (chunk_id,)
            ).fetchone() is not None

    def save(self, chunk_id: str, model: str, input_hash: str, embedding: list[float]) -> None:
        now = utc_now().isoformat()
        with self.database._connect() as connection:
            connection.execute("""INSERT INTO chunk_embeddings
                (chunk_id, model, input_hash, dimensions, embedding_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET model=excluded.model,
                input_hash=excluded.input_hash, dimensions=excluded.dimensions,
                embedding_json=excluded.embedding_json, updated_at=excluded.updated_at""",
                (chunk_id, model, input_hash, len(embedding), json.dumps(embedding), now, now))

    def delete(self, chunk_id: str) -> None:
        with self.database._connect() as connection:
            connection.execute("DELETE FROM chunk_embeddings WHERE chunk_id=?", (chunk_id,))

    def get_input_hash(self, chunk_id: str) -> str | None:
        with self.database._connect() as connection:
            row = connection.execute(
                "SELECT input_hash FROM chunk_embeddings WHERE chunk_id=?", (chunk_id,)
            ).fetchone()
            return row["input_hash"] if row else None

    def search(self, query_embedding: list[float], *, document_id: str | None = None,
               limit: int = 8) -> list[dict]:
        query = """SELECT e.embedding_json, e.model, c.id AS chunk_id, c.document_id,
                   c.position, c.title, c.summary, c.text, c.tags_json,
                   c.sources_json, d.filename
                   FROM chunk_embeddings e
                   JOIN chunks c ON c.id=e.chunk_id
                   JOIN documents d ON d.id=c.document_id"""
        values = []
        if document_id:
            query += " WHERE c.document_id=?"
            values.append(document_id)
        with self.database._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        results = []
        for row in rows:
            embedding = json.loads(row["embedding_json"])
            if len(embedding) != len(query_embedding):
                continue
            score = self._cosine(query_embedding, embedding)
            results.append({
                "score": score, "chunk_id": row["chunk_id"],
                "document_id": row["document_id"], "filename": row["filename"],
                "position": row["position"], "title": row["title"],
                "summary": row["summary"], "text": row["text"],
                "tags": json.loads(row["tags_json"]),
                "sources": json.loads(row["sources_json"]), "model": row["model"],
            })
        return sorted(results, key=lambda result: result["score"], reverse=True)[:limit]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        numerator = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0
