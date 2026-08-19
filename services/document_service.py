from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from werkzeug.utils import secure_filename

from models.document_model import DocumentInfo, DocumentModel, PageModel
from repositories.protocols import DocumentRepository
from services.pdf_extractor import extract_pdf
from services.text_preprocessing_service import TextPreprocessingService


logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, repository: DocumentRepository, data_dir: Path):
        self.repository = repository
        self.data_dir = data_dir
        self.upload_folder = data_dir / "uploads"
        self.trash_folder = data_dir / "trash"
        self.upload_folder.mkdir(parents=True, exist_ok=True)
        self.trash_folder.mkdir(parents=True, exist_ok=True)
        self.preprocessor = TextPreprocessingService()

    def get_document(self, document_id: str) -> DocumentModel:
        return self.repository.get(document_id)

    def get_documents_info(self) -> list[DocumentInfo]:
        return self.repository.list()

    def upload_document(self, file, max_pages: int = 500) -> str:
        filename = secure_filename(file.filename)
        signature = file.stream.read(5)
        file.stream.seek(0)
        if signature != b"%PDF-":
            raise ValueError("Le fichier envoyé n'est pas un PDF valide.")
        document_id = str(uuid.uuid4())
        pdf_path = self.upload_folder / f"{document_id}_{filename}"
        file.save(pdf_path)

        try:
            extracted_pages = extract_pdf(str(pdf_path), max_pages=max_pages)
        except Exception:
            pdf_path.unlink(missing_ok=True)
            raise
        corrected = self.preprocessor.process(
            [item["corrected_text"] for item in extracted_pages],
            list(self.preprocessor.DEFAULT_RULES),
        ).texts
        pages = [PageModel(
            id=str(uuid.uuid4()), page=item["page"], position=index,
            original_text=item["original_text"],
            corrected_text=corrected[index],
            status=item["status"],
        ) for index, item in enumerate(extracted_pages)]
        document = DocumentModel(
            id=document_id, filename=filename, original_path=str(pdf_path), pages=pages
        )
        self.repository.save(document)
        return document_id

    def save_pages(self, document_id: str, form: dict, expected_version: int) -> DocumentModel:
        document = self.repository.get(document_id)
        changed = False
        for page in document.pages:
            new_text = form.get(f"page_{page.id}", page.corrected_text)
            if new_text != page.corrected_text:
                page.corrected_text = new_text
                page.status = "manually_corrected"
                changed = True
        self.repository.save_pages(
            document_id, document.pages, expected_version=expected_version,
            has_chunks=changed and bool(document.chunks),
        )
        return self.repository.get(document_id)

    def preview_preprocessing(self, document_id: str, form: dict, rules: list[str]):
        document = self.repository.get(document_id)
        current_texts = [form.get(f"page_{page.id}", page.corrected_text) for page in document.pages]
        if "reset_original" in rules:
            current_texts = [page.original_text for page in document.pages]
            rules = []
        result = self.preprocessor.process(current_texts, rules)
        for page, text in zip(document.pages, result.texts, strict=True):
            page.corrected_text = text
        return document, result

    def delete_page(self, document_id: str, page_id: str, form: dict, expected_version: int) -> bool:
        document = self.repository.get(document_id)
        if not any(page.id == page_id for page in document.pages):
            return False
        for page in document.pages:
            if page.id != page_id:
                new_text = form.get(f"page_{page.id}", page.corrected_text)
                if new_text != page.corrected_text:
                    page.corrected_text = new_text
                    page.status = "manually_corrected"
        return self.repository.save_pages(
            document_id, document.pages, expected_version=expected_version,
            delete_page_id=page_id, has_chunks=bool(document.chunks),
        )

    def delete_document(self, document_id: str) -> bool:
        document = self.repository.get(document_id)
        original_path = Path(document.original_path) if document.original_path else None
        trashed_path = None
        try:
            if original_path and original_path.exists():
                resolved_upload_folder = self.upload_folder.resolve()
                resolved_original_path = original_path.resolve()
                if resolved_original_path.parent != resolved_upload_folder:
                    logger.warning("Fichier source hors du dossier uploads, non supprimé : %s", resolved_original_path)
                    self.repository.delete(document_id)
                    return False
                trashed_path = self.trash_folder / f"{uuid.uuid4()}_{resolved_original_path.name}"
                resolved_original_path.replace(trashed_path)
            self.repository.delete(document_id)
            if trashed_path:
                trashed_path.unlink(missing_ok=True)
            return True
        except Exception:
            if trashed_path and trashed_path.exists() and original_path:
                trashed_path.replace(original_path)
            logger.exception("Impossible de supprimer le fichier source %s", original_path)
            return False

    def migrate_json_documents(self, folders: list[Path]) -> int:
        existing_ids = {document.id for document in self.repository.list()}
        migrated = 0
        for folder in folders:
            if not folder.exists():
                continue
            for json_path in folder.glob("*.json"):
                try:
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                    if data["id"] in existing_ids:
                        continue
                    pages = [PageModel(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{data['id']}:page:{item['page']}")),
                        page=item["page"], position=index,
                        original_text=item.get("original_text", ""),
                        corrected_text=item.get("corrected_text", item.get("original_text", "")),
                        status=item.get("status", "ok"),
                    ) for index, item in enumerate(data.get("pages", []))]
                    upload_matches = list((folder.parent / "uploads").glob(f"{data['id']}_*"))
                    self.repository.save(DocumentModel(
                        id=data["id"], filename=data["filename"], pages=pages,
                        original_path=str(upload_matches[0]) if upload_matches else "",
                    ))
                    existing_ids.add(data["id"])
                    migrated += 1
                except (KeyError, ValueError, OSError, json.JSONDecodeError) as error:
                    logger.warning("Migration ignorée pour %s : %s", json_path.name, error)
        return migrated
