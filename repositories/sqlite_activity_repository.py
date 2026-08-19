from __future__ import annotations

import json
import uuid

from models.document_model import utc_now
from repositories.sqlite_document_repository import SQLiteDocumentRepository


class SQLiteActivityRepository:
    def __init__(self, database_path):
        self.database = SQLiteDocumentRepository(database_path)

    def record(self, event_type: str, message: str, *, severity: str = "info",
               document_id: str | None = None, chunk_id: str | None = None,
               job_id: str | None = None, details: dict | None = None) -> None:
        with self.database._connect() as connection:
            connection.execute("""INSERT INTO activity_events
                (id, event_type, severity, document_id, chunk_id, job_id,
                 message, details_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), event_type, severity, document_id, chunk_id, job_id,
                 message, json.dumps(details or {}, ensure_ascii=False), utc_now().isoformat()))

    def list_recent(self, limit: int = 100) -> list[dict]:
        with self.database._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM activity_events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) | {"details": json.loads(row["details_json"])} for row in rows]
