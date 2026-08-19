from __future__ import annotations

import logging
import uuid

from models.document_model import utc_now
from models.job_model import JobModel
from models.statuses import JobStatus
from repositories import SQLiteActivityRepository, SQLiteJobRepository
from services.chunk_service import ChunkService


logger = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


class JobService:
    def __init__(self, repository: SQLiteJobRepository, chunks: ChunkService,
                 activity: SQLiteActivityRepository, ocr_service=None, correction_service=None,
                 publication_service=None):
        self.repository = repository
        self.chunks = chunks
        self.activity = activity
        self.ocr_service = ocr_service
        self.correction_service = correction_service
        self.publication_service = publication_service

    def enqueue(self, job_type: str, *, document_id: str | None = None,
                chunk_id: str | None = None, payload: dict | None = None) -> JobModel:
        job = JobModel(id=str(uuid.uuid4()), job_type=job_type,
                       document_id=document_id, chunk_id=chunk_id, payload=payload or {})
        self.repository.create(job)
        self.activity.record("job.queued", f"Job {job_type} ajouté à la file.",
                             document_id=document_id, chunk_id=chunk_id, job_id=job.id)
        return job

    def run_next(self, worker_id: str) -> bool:
        job = self.repository.claim_next(worker_id)
        if job is None:
            return False
        self._execute(job)
        return True

    def resume_interrupted(self) -> int:
        return len(self.repository.reset_interrupted())

    def cancel(self, job_id: str) -> bool:
        cancelled = self.repository.request_cancel(job_id)
        if cancelled:
            self.activity.record("job.cancel_requested", "Annulation du job demandée.", job_id=job_id)
        return cancelled

    def _execute(self, job: JobModel) -> None:
        self.activity.record("job.started", f"Job {job.job_type} démarré.",
                             document_id=job.document_id, chunk_id=job.chunk_id, job_id=job.id)
        try:
            result = self._dispatch(job)
            job.payload["result"] = result
            job.progress_current = job.progress_total or 1
            job.progress_total = job.progress_total or 1
            job.status = JobStatus.COMPLETED
            self.activity.record("job.completed", f"Job {job.job_type} terminé.",
                                 document_id=job.document_id, chunk_id=job.chunk_id,
                                 job_id=job.id, details=result)
        except JobCancelled:
            job.status = JobStatus.CANCELLED
            job.error_message = "Traitement annulé."
            self.activity.record("job.cancelled", f"Job {job.job_type} annulé.",
                                 document_id=job.document_id, job_id=job.id)
        except Exception as error:
            logger.exception("Échec du job %s (%s)", job.id, job.job_type)
            job.status = JobStatus.FAILED
            job.error_message = self._safe_error(error)
            self.activity.record("job.failed", f"Échec du job {job.job_type}.", severity="error",
                                 document_id=job.document_id, chunk_id=job.chunk_id, job_id=job.id)
        finally:
            job.finished_at = utc_now()
            self.repository.update(job)

    def _dispatch(self, job: JobModel):
        progress = lambda current, total, stage: self._progress(job, current, total, stage)
        if job.job_type == "generate_document":
            return {"chunks": self.chunks.generate(job.document_id, on_progress=progress)}
        if job.job_type == "generate_all":
            documents, chunks = self.chunks.generate_missing(on_progress=progress)
            return {"documents": documents, "chunks": chunks}
        if job.job_type == "enrich_document":
            return {"chunks": self.chunks.enrich_document(job.document_id, on_progress=progress)}
        if job.job_type == "enrich_chunk":
            self.chunks.enrich_chunk(job.document_id, job.chunk_id)
            return {"chunks": 1}
        if job.job_type == "vectorize_document":
            return {"chunks": self.chunks.vectorize_document(job.document_id, on_progress=progress)}
        if job.job_type == "vectorize_all":
            documents, chunks = self.chunks.vectorize_all(on_progress=progress)
            return {"documents": documents, "chunks": chunks}
        if job.job_type == "publish_document" and self.publication_service:
            return {"chunks": self.publication_service.publish_document(
                job.document_id, on_progress=progress
            )}
        if job.job_type == "ocr_document" and self.ocr_service:
            return self.ocr_service.process_document(job.document_id, on_progress=progress)
        if job.job_type == "correct_document_ai" and self.correction_service:
            return self.correction_service.correct_document(job.document_id, on_progress=progress)
        if job.job_type == "correct_page_ai" and self.correction_service:
            return self.correction_service.correct_page(
                job.document_id, job.payload["page_id"],
                expected_text=job.payload.get("expected_text"),
            )
        raise ValueError("Type de job inconnu.")

    def _progress(self, job: JobModel, current: int, total: int, stage: str) -> None:
        if self.repository.cancellation_requested(job.id):
            raise JobCancelled()
        job.progress_current = current
        job.progress_total = total
        job.payload["stage"] = stage
        self.repository.update(job)

    @staticmethod
    def _safe_error(error: Exception) -> str:
        if isinstance(error, RuntimeError) and "OPENAI_API_KEY" in str(error):
            return "La clé OpenAI n'est pas configurée."
        if "Tesseract" in str(error):
            return str(error)
        if "Qdrant" in str(error) or "Pinecone" in str(error) or "vectorielle distante" in str(error):
            return str(error)
        return "Le traitement a échoué. Consultez les logs du serveur."
