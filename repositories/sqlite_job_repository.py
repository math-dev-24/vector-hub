from __future__ import annotations

import json

from models.document_model import utc_now
from models.job_model import JobModel
from repositories.sqlite_document_repository import SQLiteDocumentRepository


class SQLiteJobRepository:
    def __init__(self, database_path):
        self.database = SQLiteDocumentRepository(database_path)

    def create(self, job: JobModel) -> None:
        with self.database._connect() as connection:
            connection.execute("""INSERT INTO jobs
                (id, job_type, document_id, chunk_id, status, progress_current,
                 progress_total, error_message, payload_json, created_at, started_at, finished_at,
                 cancel_requested, worker_id, api_calls, input_tokens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job.id, job.job_type, job.document_id, job.chunk_id, job.status,
                 job.progress_current, job.progress_total, job.error_message,
                 json.dumps(job.payload, ensure_ascii=False), job.created_at.isoformat(),
                 job.started_at.isoformat() if job.started_at else None,
                 job.finished_at.isoformat() if job.finished_at else None,
                 int(job.cancel_requested), job.worker_id, job.api_calls, job.input_tokens))

    def get(self, job_id: str) -> JobModel:
        with self.database._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._row(row)

    def list_recent(self, document_id: str | None = None, limit: int = 20) -> list[JobModel]:
        query = "SELECT * FROM jobs"
        values: list = []
        if document_id:
            query += " WHERE document_id=?"
            values.append(document_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        values.append(limit)
        with self.database._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row(row) for row in rows]

    def update(self, job: JobModel) -> None:
        with self.database._connect() as connection:
            connection.execute("""UPDATE jobs SET status=?, progress_current=?, progress_total=?,
                error_message=?, payload_json=?, started_at=?, finished_at=?, cancel_requested=?,
                worker_id=?, api_calls=?, input_tokens=? WHERE id=?""",
                (job.status, job.progress_current, job.progress_total, job.error_message,
                 json.dumps(job.payload, ensure_ascii=False),
                 job.started_at.isoformat() if job.started_at else None,
                 job.finished_at.isoformat() if job.finished_at else None,
                 int(job.cancel_requested), job.worker_id, job.api_calls, job.input_tokens, job.id))

    def claim_next(self, worker_id: str) -> JobModel | None:
        with self.database._connect() as connection:
            row = connection.execute("""UPDATE jobs SET status='running', worker_id=?,
                started_at=?, error_message=NULL
                WHERE id=(SELECT id FROM jobs WHERE status='pending' AND cancel_requested=0
                          ORDER BY created_at LIMIT 1)
                RETURNING *""", (worker_id, utc_now().isoformat())).fetchone()
        return self._row(row) if row else None

    def request_cancel(self, job_id: str) -> bool:
        with self.database._connect() as connection:
            result = connection.execute("""UPDATE jobs SET cancel_requested=1,
                status=CASE WHEN status='pending' THEN 'cancelled' ELSE status END,
                finished_at=CASE WHEN status='pending' THEN ? ELSE finished_at END
                WHERE id=? AND status IN ('pending', 'running')""",
                (utc_now().isoformat(), job_id))
            return result.rowcount > 0

    def cancellation_requested(self, job_id: str) -> bool:
        with self.database._connect() as connection:
            row = connection.execute(
                "SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def reset_interrupted(self) -> list[JobModel]:
        with self.database._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status='pending', started_at=NULL WHERE status='running'"
            )
            rows = connection.execute(
                "SELECT * FROM jobs WHERE status='pending' ORDER BY created_at"
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> JobModel:
        return JobModel(
            id=row["id"], job_type=row["job_type"], document_id=row["document_id"],
            chunk_id=row["chunk_id"], status=row["status"],
            progress_current=row["progress_current"], progress_total=row["progress_total"],
            error_message=row["error_message"], payload=json.loads(row["payload_json"]),
            created_at=row["created_at"], started_at=row["started_at"], finished_at=row["finished_at"],
            cancel_requested=bool(row["cancel_requested"]), worker_id=row["worker_id"],
            api_calls=row["api_calls"], input_tokens=row["input_tokens"],
        )
