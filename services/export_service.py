from __future__ import annotations

import io
import json

from repositories.protocols import DocumentRepository


class ExportService:
    def __init__(self, documents: DocumentRepository):
        self.documents = documents

    def rag_jsonl(self, document_id: str) -> tuple[io.BytesIO, str]:
        document = self.documents.get(document_id)
        lines = [json.dumps({
            "id": chunk.id,
            "document_id": document.id,
            "filename": document.filename,
            "position": chunk.position,
            "text": chunk.text,
            "title": chunk.title,
            "summary": chunk.summary,
            "category": chunk.category,
            "tags": chunk.tags,
            "keywords": chunk.keywords,
            "section_path": chunk.section_path,
            "sources": [source.model_dump() for source in chunk.sources],
            "token_count": chunk.token_count,
            "content_hash": chunk.content_hash,
            "provenance_status": chunk.provenance_status,
        }, ensure_ascii=False) for chunk in document.chunks]
        stream = io.BytesIO(("\n".join(lines) + ("\n" if lines else "")).encode("utf-8"))
        filename = document.filename.rsplit(".", 1)[0] + ".jsonl"
        return stream, filename
