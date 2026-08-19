from __future__ import annotations

import os
from collections.abc import Callable

from openai import OpenAI
from pydantic import BaseModel, Field

from models.document_model import ChunkModel


class GeneratedChunkMetadata(BaseModel):
    title: str
    summary: str
    category: str
    tags: list[str] = Field(max_length=8)
    keywords: list[str] = Field(max_length=12)


class OpenAIMetadataService:
    PROMPT_VERSION = "metadata-v2"

    def __init__(self):
        self.model = os.environ.get("OPENAI_METADATA_MODEL", "gpt-5-mini")
        self.client = OpenAI(max_retries=3, timeout=60) if self.is_configured() else None

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def enrich(self, chunks: list[ChunkModel], *, force: bool = False,
               on_enriched: Callable[[ChunkModel], None] | None = None) -> None:
        if not self.is_configured():
            raise RuntimeError("OPENAI_API_KEY n'est pas configurée.")
        client = self.client or OpenAI(max_retries=3, timeout=60)
        for index, chunk in enumerate(chunks):
            previous_title = chunks[index - 1].title if index > 0 else ""
            response = client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": (
                        "Tu structures des fragments documentaires français pour un système RAG. "
                        "Produis un titre précis, un résumé factuel, une catégorie courte, des tags "
                        "métier et des mots-clés. N'invente aucune information absente du texte."
                    )},
                    {"role": "user", "content": (
                        f"Document: chunk {chunk.position + 1}.\n"
                        f"Section précédente: {previous_title or 'aucune'}.\n\n"
                        f"Texte:\n{chunk.text}"
                    )},
                ],
                text_format=GeneratedChunkMetadata,
            )
            metadata = response.output_parsed
            if metadata is None:
                raise RuntimeError(f"Métadonnées absentes pour le chunk {chunk.position + 1}.")
            if force or chunk.title_source != "manual":
                chunk.title = metadata.title
                chunk.title_source = "ai"
            if force or chunk.summary_source != "manual":
                chunk.summary = metadata.summary
                chunk.summary_source = "ai"
            if force or chunk.category_source != "manual":
                chunk.category = metadata.category
                chunk.category_source = "ai"
            if force or chunk.tags_source != "manual":
                chunk.tags = metadata.tags
                chunk.tags_source = "ai"
            chunk.keywords = metadata.keywords
            chunk.metadata_status = "generated"
            chunk.metadata_model = self.model
            chunk.metadata_prompt_version = self.PROMPT_VERSION
            if on_enriched:
                on_enriched(chunk)
