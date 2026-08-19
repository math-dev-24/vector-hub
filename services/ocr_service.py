from __future__ import annotations

import os
import shutil

import pymupdf

from repositories.protocols import DocumentRepository


class OCRService:
    def __init__(self, documents: DocumentRepository):
        self.documents = documents
        self.language = os.environ.get("OCR_LANGUAGE", "fra+eng")
        self.dpi = int(os.environ.get("OCR_DPI", "300"))

    @staticmethod
    def is_available() -> bool:
        return shutil.which("tesseract") is not None

    def process_document(self, document_id: str, on_progress=None) -> dict:
        if not self.is_available():
            raise RuntimeError("Tesseract n'est pas installé. L'OCR local est indisponible.")
        document = self.documents.get(document_id)
        if not document.original_path:
            raise RuntimeError("Le PDF source est introuvable.")
        targets = [page for page in document.pages if not page.corrected_text.strip()]
        if not targets:
            return {"pages": 0, "message": "Aucune page vide à OCRiser."}

        pdf = pymupdf.open(document.original_path)
        completed = 0
        try:
            for page_model in targets:
                page_model.ocr_status = "processing"
                self.documents.update_page(document_id, page_model)
                pdf_page = pdf[page_model.page - 1]
                text_page = pdf_page.get_textpage_ocr(
                    language=self.language, dpi=self.dpi, full=True
                )
                text = pdf_page.get_text("text", textpage=text_page)
                page_model.original_text = text
                page_model.corrected_text = text
                page_model.extraction_method = "ocr"
                page_model.ocr_status = "completed" if text.strip() else "empty"
                page_model.status = "ok" if text.strip() else "warning"
                self.documents.update_page(document_id, page_model)
                completed += 1
                if on_progress:
                    on_progress(completed, len(targets), "OCR local")
        finally:
            pdf.close()

        if document.chunks:
            self.documents.update_statuses(
                document_id, chunks_status="outdated", vector_status="outdated"
            )
        return {"pages": completed}
