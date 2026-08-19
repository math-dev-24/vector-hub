from __future__ import annotations

import os

from openai import OpenAI

from repositories.protocols import VectorRepository


class SearchService:
    def __init__(self, vectors: VectorRepository):
        self.vectors = vectors
        self.model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    def search(self, query: str, *, document_id: str | None = None, limit: int = 8) -> list[dict]:
        query = query.strip()
        if not query:
            return []
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY n'est pas configurée.")
        response = OpenAI(max_retries=3, timeout=30).embeddings.create(
            model=self.model, input=query
        )
        return self.vectors.search(
            response.data[0].embedding, document_id=document_id, limit=max(1, min(limit, 20))
        )
