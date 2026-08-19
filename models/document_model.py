from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field
from models.statuses import ChunksStatus, EmbeddingStatus, MetadataStatus, PagesStatus, ProvenanceStatus, VectorStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PageModel(BaseModel):
    id: str
    page: int
    position: int
    original_text: str
    corrected_text: str
    status: str = "ok"
    extraction_method: str = "text_layer"
    ocr_status: str = "not_needed"


class ChunkSourceModel(BaseModel):
    page_id: str
    page_number: int
    start_offset: int = 0
    end_offset: int = 0


class ChunkModel(BaseModel):
    id: str
    document_id: str
    position: int
    text: str
    title: str = ""
    summary: str = ""
    category: str = ""
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    section_path: list[str] = Field(default_factory=list)
    sources: list[ChunkSourceModel] = Field(default_factory=list)
    token_count: int = 0
    content_hash: str = ""
    metadata_status: MetadataStatus = MetadataStatus.PENDING
    manually_reviewed: bool = False
    metadata_model: str | None = None
    metadata_prompt_version: str | None = None
    title_source: str = "automatic"
    summary_source: str = "automatic"
    category_source: str = "automatic"
    tags_source: str = "automatic"
    provenance_status: ProvenanceStatus = ProvenanceStatus.EXACT
    embedding_status: EmbeddingStatus = EmbeddingStatus.MISSING
    embedded_content_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DocumentModel(BaseModel):
    id: str
    filename: str
    original_path: str = ""
    pages_status: PagesStatus = PagesStatus.DRAFT
    chunks_status: ChunksStatus = ChunksStatus.MISSING
    vector_status: VectorStatus = VectorStatus.MISSING
    version: int = 0
    pages: list[PageModel] = Field(default_factory=list)
    chunks: list[ChunkModel] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DocumentInfo(BaseModel):
    id: str
    filename: str
    pages_count: int
    chunks_count: int = 0
    pages_status: PagesStatus = PagesStatus.DRAFT
    chunks_status: ChunksStatus = ChunksStatus.MISSING
    vector_status: VectorStatus = VectorStatus.MISSING
    updated_at: datetime = Field(default_factory=utc_now)
