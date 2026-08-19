from __future__ import annotations

import os

from openai import OpenAI
from pydantic import BaseModel, Field

from repositories.protocols import DocumentRepository
from services.text_preprocessing_service import TextPreprocessingService


class CorrectedPage(BaseModel):
    corrected_text: str
    notes: list[str] = Field(default_factory=list, max_length=8)


class OpenAIPageCorrectionService:
    PROMPT_VERSION = "page-cleanup-v1"

    def __init__(self, documents: DocumentRepository):
        self.documents = documents
        self.model = os.environ.get("OPENAI_CORRECTION_MODEL", "gpt-5.4-nano")
        self.client = OpenAI(max_retries=3, timeout=120) if self.is_configured() else None
        self.rules = TextPreprocessingService()

    @staticmethod
    def is_configured() -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def correct_document(self, document_id: str, on_progress=None) -> dict:
        document = self.documents.get(document_id)
        completed = 0
        skipped = 0
        for page in document.pages:
            result = self.correct_page(document_id, page.id, expected_text=page.corrected_text)
            completed += int(result["updated"])
            skipped += int(not result["updated"])
            if on_progress:
                on_progress(completed + skipped, len(document.pages), "pré-correction IA")
        return {"pages": completed, "skipped": skipped}

    def correct_page(self, document_id: str, page_id: str,
                     expected_text: str | None = None) -> dict:
        if not self.is_configured():
            raise RuntimeError("OPENAI_API_KEY n'est pas configurée.")
        document = self.documents.get(document_id)
        page = next((item for item in document.pages if item.id == page_id), None)
        if page is None:
            raise KeyError(page_id)
        if expected_text is not None and page.corrected_text != expected_text:
            return {"updated": False, "reason": "La page a été modifiée pendant le traitement."}

        deterministic = self.rules.process(
            [page.corrected_text], list(self.rules.DEFAULT_RULES)
        ).texts[0]
        if not deterministic.strip():
            return {"updated": False, "reason": "Page sans texte."}
        client = self.client or OpenAI(max_retries=3, timeout=120)
        response = client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": (
                    "Tu corriges une extraction PDF/OCR avant indexation RAG. Corrige uniquement "
                    "les artefacts certains: caractères OCR erronés évidents, espaces, ponctuation, "
                    "mots coupés et retours de ligne. Préserve intégralement le sens, les nombres, "
                    "noms propres, titres, listes et langue. Ne résume pas, ne complète rien et "
                    "n'ajoute aucune information. En cas de doute, conserve le texte reçu."
                )},
                {"role": "user", "content": f"Texte extrait de la page {page.page}:\n\n{deterministic}"},
            ],
            text_format=CorrectedPage,
        )
        correction = response.output_parsed
        if correction is None or not correction.corrected_text.strip():
            raise RuntimeError("La pré-correction IA n'a retourné aucun texte.")

        latest = self.documents.get(document_id)
        latest_page = next(item for item in latest.pages if item.id == page_id)
        if expected_text is not None and latest_page.corrected_text != expected_text:
            return {"updated": False, "reason": "La page a été modifiée pendant le traitement."}
        latest_page.corrected_text = correction.corrected_text
        latest_page.status = "ai_corrected"
        self.documents.update_page(document_id, latest_page)
        if latest.chunks:
            self.documents.update_statuses(document_id, chunks_status="outdated", vector_status="outdated")
        return {"updated": True, "notes": correction.notes, "model": self.model,
                "prompt_version": self.PROMPT_VERSION}
