from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from models.document_model import utc_now
from models.statuses import JobStatus


class JobModel(BaseModel):
    id: str
    job_type: str
    document_id: str | None = None
    chunk_id: str | None = None
    status: JobStatus = JobStatus.PENDING
    progress_current: int = 0
    progress_total: int = 0
    error_message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool = False
    worker_id: str | None = None
    api_calls: int = 0
    input_tokens: int = 0
