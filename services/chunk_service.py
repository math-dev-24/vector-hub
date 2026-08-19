from __future__ import annotations

import uuid
from collections.abc import Callable

from models.document_model import ChunkModel, utc_now
from repositories.protocols import DocumentRepository, VectorRepository
from services.chunking_service import ChunkingService
from services.openai_metadata_service import OpenAIMetadataService
from services.vectorization_service import VectorizationService


class ChunkService:
    def __init__(self, repository: DocumentRepository, vector_repository: VectorRepository):
        self.repository = repository
        self.vectors = vector_repository
        self.chunker = ChunkingService()
        self.metadata = OpenAIMetadataService()
        self.vectorizer = VectorizationService(repository, vector_repository)

    def generate(self, document_id: str, with_metadata: bool = True,
                 on_progress: Callable[[int, int, str], None] | None = None) -> int:
        document = self.repository.get(document_id)
        self.repository.update_statuses(document_id, chunks_status="generating")
        try:
            chunks = self.chunker.generate(document)
        except Exception:
            self.repository.update_statuses(document_id, chunks_status="error")
            raise
        self.repository.replace_chunks(document_id, chunks)
        self.repository.update_statuses(document_id, chunks_status="ready", vector_status="missing")
        if on_progress:
            on_progress(0, len(chunks), "métadonnées OpenAI" if with_metadata else "chunking")
        if with_metadata and chunks:
            try:
                completed = 0
                def persist(chunk):
                    nonlocal completed
                    self.repository.update_chunk(chunk)
                    completed += 1
                    if on_progress:
                        on_progress(completed, len(chunks), "métadonnées OpenAI")
                self.metadata.enrich(chunks, on_enriched=persist)
            except Exception:
                for chunk in chunks:
                    if chunk.metadata_status != "generated":
                        chunk.metadata_status = "error"
                    self.repository.update_chunk(chunk)
                self.repository.update_statuses(document_id, chunks_status="error")
                raise
        return len(chunks)

    def generate_missing(self, on_progress=None) -> tuple[int, int]:
        documents_count = chunks_count = 0
        targets = [info for info in self.repository.list()
                   if info.chunks_status in {"missing", "outdated"}]
        for index, info in enumerate(targets):
            if info.chunks_status in {"missing", "outdated"}:
                chunks_count += self.generate(info.id)
                documents_count += 1
                if on_progress:
                    on_progress(index + 1, len(targets), "documents chunkés")
        return documents_count, chunks_count

    def enrich_document(self, document_id: str, on_progress=None) -> int:
        document = self.repository.get(document_id)
        if not document.chunks:
            raise ValueError("Aucun chunk à enrichir.")
        self.repository.update_statuses(document_id, chunks_status="generating")
        try:
            completed = 0
            def persist(chunk):
                nonlocal completed
                self.repository.update_chunk(chunk)
                completed += 1
                if on_progress:
                    on_progress(completed, len(document.chunks), "métadonnées OpenAI")
            self.metadata.enrich(document.chunks, on_enriched=persist)
        except Exception:
            self.repository.update_statuses(document_id, chunks_status="error")
            raise
        for chunk in document.chunks:
            if self.vectors.exists(chunk.id):
                chunk.embedding_status = "outdated"
            self.repository.update_chunk(chunk)
        self.repository.update_statuses(
            document_id, chunks_status="ready",
            vector_status="outdated" if any(chunk.embedding_status == "outdated" for chunk in document.chunks) else None,
        )
        return len(document.chunks)

    def enrich_chunk(self, document_id: str, chunk_id: str) -> None:
        document = self.repository.get(document_id)
        chunk = self._find(document.chunks, chunk_id)
        old_embedding_payload = self.vectorizer._embedding_text(chunk)

        self.metadata.enrich([chunk], force=True)
        chunk.manually_reviewed = False
        chunk.updated_at = utc_now()

        if self.vectorizer._embedding_text(chunk) != old_embedding_payload:
            has_vector = self.vectors.exists(chunk.id)
            chunk.embedding_status = "outdated" if has_vector else "missing"
            if has_vector:
                self.repository.update_statuses(document_id, vector_status="outdated")

        if all(item.metadata_status not in {"pending", "error"} for item in document.chunks):
            self.repository.update_statuses(document_id, chunks_status="ready")
        self.repository.update_chunk(chunk)

    def update(self, document_id: str, chunk_id: str, form: dict,
               expected_version: int | None = None) -> None:
        document = self.repository.get(document_id)
        chunk = self._find(document.chunks, chunk_id)
        old_embedding_payload = self.vectorizer._embedding_text(chunk)
        chunk.title = form.get("title", "").strip()
        chunk.summary = form.get("summary", "").strip()
        chunk.category = form.get("category", "").strip()
        chunk.text = form.get("text", "").strip()
        chunk.tags = self._parse_list(form.get("tags", ""))
        chunk.keywords = self._parse_list(form.get("keywords", ""))
        chunk.token_count = self.chunker.estimate_tokens(chunk.text)
        chunk.content_hash = self.chunker.content_hash(chunk.text)
        chunk.metadata_status = "manually_edited"
        chunk.manually_reviewed = True
        chunk.title_source = "manual"
        chunk.summary_source = "manual"
        chunk.category_source = "manual"
        chunk.tags_source = "manual"
        chunk.updated_at = utc_now()
        embedding_changed = self.vectorizer._embedding_text(chunk) != old_embedding_payload
        if embedding_changed:
            chunk.embedding_status = "outdated" if self.vectors.exists(chunk.id) else "missing"
        metadata_ready = all(item.metadata_status not in {"pending", "error"} for item in document.chunks)
        self.repository.update_chunk(chunk, expected_version=expected_version)
        self.repository.update_statuses(
            document_id,
            vector_status="outdated" if embedding_changed else None,
            chunks_status="ready" if metadata_ready else None,
        )

    def delete(self, document_id: str, chunk_id: str) -> None:
        document = self.repository.get(document_id)
        self.repository.delete_chunk(document_id, chunk_id)
        self.repository.update_statuses(document_id, vector_status="outdated")

    def merge_with_next(self, document_id: str, chunk_id: str) -> None:
        document = self.repository.get(document_id)
        index = next(index for index, chunk in enumerate(document.chunks) if chunk.id == chunk_id)
        if index >= len(document.chunks) - 1:
            raise ValueError("Aucun chunk suivant à fusionner.")
        first, second = document.chunks[index], document.chunks[index + 1]
        first.text = f"{first.text}\n\n{second.text}".strip()
        first.sources.extend(source for source in second.sources if source not in first.sources)
        first.token_count = self.chunker.estimate_tokens(first.text)
        first.content_hash = self.chunker.content_hash(first.text)
        first.metadata_status = "pending"
        first.embedding_status = "outdated" if self.vectors.exists(first.id) else "missing"
        first.provenance_status = "approximate"
        self.repository.update_chunk(first)
        self.repository.delete_chunk(document_id, second.id)
        self.repository.update_statuses(document_id, chunks_status="outdated", vector_status="outdated")

    def split(self, document_id: str, chunk_id: str, offset: int) -> None:
        document = self.repository.get(document_id)
        index = next(index for index, chunk in enumerate(document.chunks) if chunk.id == chunk_id)
        chunk = document.chunks[index]
        if offset < 1 or offset >= len(chunk.text):
            raise ValueError("Position de découpe invalide.")
        first_text, second_text = chunk.text[:offset].strip(), chunk.text[offset:].strip()
        if not first_text or not second_text:
            raise ValueError("Les deux chunks doivent contenir du texte.")
        chunk.text = first_text
        chunk.content_hash = self.chunker.content_hash(first_text)
        chunk.token_count = self.chunker.estimate_tokens(first_text)
        chunk.metadata_status = "pending"
        chunk.embedding_status = "outdated" if self.vectors.exists(chunk.id) else "missing"
        chunk.provenance_status = "approximate"
        new_chunk = ChunkModel(
            id=str(uuid.uuid4()), document_id=document.id, position=index + 1,
            text=second_text, sources=[source.model_copy(deep=True) for source in chunk.sources],
            token_count=self.chunker.estimate_tokens(second_text),
            content_hash=self.chunker.content_hash(second_text),
            provenance_status="approximate",
        )
        self.repository.update_chunk(chunk)
        self.repository.insert_chunk(new_chunk)
        self.repository.update_statuses(document_id, chunks_status="outdated", vector_status="outdated")

    def vectorize_document(self, document_id: str, on_progress=None) -> int:
        document = self.repository.get(document_id)
        if not document.chunks:
            self.repository.update_statuses(document_id, vector_status="missing")
            return 0
        self.repository.update_statuses(document_id, vector_status="processing")
        try:
            count = self.vectorizer.vectorize(document.chunks, on_progress=on_progress)
        except Exception:
            self.repository.update_statuses(document_id, vector_status="error")
            raise
        statuses = {chunk.embedding_status for chunk in document.chunks}
        self.repository.update_statuses(
            document_id, vector_status="ready" if statuses <= {"ready"} else "partial"
        )
        return count

    def vectorize_all(self, on_progress=None) -> tuple[int, int]:
        documents_count = chunks_count = 0
        targets = [info for info in self.repository.list()
                   if info.chunks_count and info.vector_status != "ready"]
        for index, info in enumerate(targets):
            if info.chunks_count and info.vector_status != "ready":
                chunks_count += self.vectorize_document(info.id)
                documents_count += 1
                if on_progress:
                    on_progress(index + 1, len(targets), "documents vectorisés")
        return documents_count, chunks_count

    @staticmethod
    def _find(chunks: list[ChunkModel], chunk_id: str) -> ChunkModel:
        return next(chunk for chunk in chunks if chunk.id == chunk_id)

    @staticmethod
    def _parse_list(value: str) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))

    @staticmethod
    def _reorder(chunks: list[ChunkModel]) -> None:
        for position, chunk in enumerate(chunks):
            chunk.position = position
