import tempfile
import unittest
import uuid
import io
from pathlib import Path
from unittest.mock import patch

from app import create_app
from models.document_model import DocumentModel, PageModel


class RoutesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.temp_dir.name))
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()
        self.document = DocumentModel(
            id=str(uuid.uuid4()), filename="routes.pdf",
            pages=[
                PageModel(id=str(uuid.uuid4()), page=1, position=0,
                          original_text="Page une", corrected_text="Page une"),
                PageModel(id=str(uuid.uuid4()), page=2, position=1,
                          original_text="Page deux", corrected_text="Page deux"),
            ],
        )
        self.app.extensions["repository"].save(self.document)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pages_and_chunks_tabs_render(self):
        pages = self.client.get(f"/documents/{self.document.id}?tab=pages")
        chunks = self.client.get(f"/documents/{self.document.id}?tab=chunks")
        self.assertEqual(pages.status_code, 200)
        self.assertIn(b"Version corrig", pages.data)
        self.assertEqual(chunks.status_code, 200)
        self.assertIn(b"Aucun chunk", chunks.data)
        self.assertEqual(self.client.get("/activity").status_code, 200)

    def test_activity_uses_document_name_and_hides_internal_ids(self):
        activity = self.app.extensions["activity_repository"]
        activity.record(
            "page.deleted", "Page supprimée.", document_id=self.document.id,
            details={"page_id": "internal-page-id", "pages": 2},
        )

        response = self.client.get("/activity")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"routes.pdf", response.data)
        self.assertIn(b"Pages : 2", response.data)
        self.assertNotIn(self.document.id.encode(), response.data)
        self.assertNotIn(b"internal-page-id", response.data)

    def test_first_page_can_be_deleted(self):
        first_page = self.document.pages[0]
        response = self.client.post(
            f"/documents/{self.document.id}/pages/{first_page.id}/delete",
            data={
                "version": self.app.extensions["repository"].get(self.document.id).version,
                f"page_{self.document.pages[1].id}": "Page deux corrigée",
            },
        )
        self.assertEqual(response.status_code, 302)
        saved = self.app.extensions["repository"].get(self.document.id)
        self.assertEqual([page.page for page in saved.pages], [2])
        self.assertEqual(saved.pages[0].corrected_text, "Page deux corrigée")

    def test_chunk_tab_after_generation(self):
        count = self.app.extensions["chunk_service"].generate(self.document.id, with_metadata=False)
        response = self.client.get(f"/documents/{self.document.id}?tab=chunks")
        self.assertGreater(count, 0)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enregistrer ce chunk", response.data)

    def test_document_deletion_cascades(self):
        source_path = Path(self.temp_dir.name) / "uploads" / "source.pdf"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"pdf")
        self.document.original_path = str(source_path)
        self.app.extensions["repository"].save(self.document)
        self.app.extensions["chunk_service"].generate(self.document.id, with_metadata=False)

        response = self.client.post(f"/documents/{self.document.id}/delete")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(source_path.exists())
        with self.assertRaises(KeyError):
            self.app.extensions["repository"].get(self.document.id)

    def test_jsonl_export(self):
        self.app.extensions["chunk_service"].generate(self.document.id, with_metadata=False)
        response = self.client.get(f"/documents/{self.document.id}/export.jsonl")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/x-ndjson")
        self.assertIn(b'"document_id"', response.data)

    def test_invalid_pdf_signature_is_rejected(self):
        response = self.client.post(
            "/upload",
            data={"pdf": (io.BytesIO(b"not a pdf"), "fake.pdf")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.app.extensions["repository"].list()), 1)

    def test_multiple_files_are_processed_independently(self):
        document_service = self.app.extensions["document_service"]
        with patch.object(
            document_service, "upload_document",
            side_effect=[str(uuid.uuid4()), str(uuid.uuid4())],
        ) as upload:
            response = self.client.post(
                "/upload",
                data={"pdfs": [
                    (io.BytesIO(b"%PDF-a"), "a.pdf"),
                    (io.BytesIO(b"%PDF-b"), "b.pdf"),
                ]},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(upload.call_count, 2)


class CsrfTest(unittest.TestCase):
    def test_post_without_token_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory))
            app.config["TESTING"] = True
            response = app.test_client().post("/chunks/generate-all")
            self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
