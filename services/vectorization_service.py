from __future__ import annotations

import os
import hashlib
from collections.abc import Callable

from openai import OpenAI

from models.document_model import ChunkModel
from repositories.protocols import DocumentRepository, VectorRepository


class VectorizationService:
    def __init__(self, document_repository: DocumentRepository, vector_repository: VectorRepository):
        self.model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.documents = document_repository
        self.vectors = vector_repository

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def vectorize(self, chunks: list[ChunkModel],
                  on_progress: Callable[[int, int, str], None] | None = None) -> int:
        if not self.is_configured():
            raise RuntimeError("OPENAI_API_KEY n'est pas configurée.")
        targets = [chunk for chunk in chunks if chunk.embedding_status in {"missing", "outdated", "error"}]
        if not targets:
            return 0
        client = OpenAI()
        completed = 0
        for start in range(0, len(targets), 100):
            batch = targets[start:start + 100]
            response = client.embeddings.create(
                model=self.model,
                input=[self._embedding_text(chunk) for chunk in batch],
            )
            for chunk, result in zip(batch, response.data, strict=True):
                input_hash = self.embedding_input_hash(chunk)
                self.vectors.save(chunk.id, self.model, input_hash, result.embedding)
                chunk.embedding_status = "ready"
                chunk.embedded_content_hash = input_hash
                self.documents.update_chunk(chunk)
                completed += 1
                if on_progress:
                    on_progress(completed, len(targets), "vectorisation")
        return len(targets)

    @staticmethod
    def _embedding_text(chunk: ChunkModel) -> str:
        metadata = "\n".join(filter(None, [
            chunk.title,
            chunk.summary,
            f"Catégorie: {chunk.category}" if chunk.category else "",
            f"Tags: {', '.join(chunk.tags)}" if chunk.tags else "",
        ]))
        return f"{metadata}\n\n{chunk.text}".strip()

    @classmethod
    def embedding_input_hash(cls, chunk: ChunkModel) -> str:
        return hashlib.sha256(cls._embedding_text(chunk).encode("utf-8")).hexdigest()
