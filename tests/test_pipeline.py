import tempfile
import unittest
import uuid
import sqlite3
from contextlib import closing
from pathlib import Path

from models.document_model import DocumentModel, PageModel
from repositories import SQLiteDocumentRepository, SQLiteVectorRepository
from services.chunk_service import ChunkService
from services.chunking_service import ChunkingService
from services.text_preprocessing_service import TextPreprocessingService


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = SQLiteDocumentRepository(Path(self.temp_dir.name) / "test.db")
        self.vector_repository = SQLiteVectorRepository(Path(self.temp_dir.name) / "test.db")
        self.document = DocumentModel(
            id=str(uuid.uuid4()), filename="test.pdf",
            pages=[
                PageModel(id=str(uuid.uuid4()), page=1, position=0,
                          original_text="ARTICLE 1\n\nDébut du contrat.",
                          corrected_text="ARTICLE 1\n\nDébut du contrat."),
                PageModel(id=str(uuid.uuid4()), page=2, position=1,
                          original_text="Suite du contrat.", corrected_text="Suite du contrat."),
            ],
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_repository_round_trip(self):
        self.repository.save(self.document)
        loaded = self.repository.get(self.document.id)
        self.assertEqual(loaded.filename, "test.pdf")
        self.assertEqual([page.page for page in loaded.pages], [1, 2])
        self.assertEqual(self.repository.list()[0].pages_count, 2)
        with closing(sqlite3.connect(self.repository.database_path)) as connection:
            versions = [row[0] for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )]
        self.assertEqual(versions, ["001", "002", "003", "004", "005", "006", "007"])

    def test_chunk_can_span_pages(self):
        chunks = ChunkingService().generate(self.document)
        self.assertEqual(len(chunks), 1)
        self.assertEqual({source.page_number for source in chunks[0].sources}, {1, 2})

    def test_chunk_edit_invalidates_embedding(self):
        self.repository.save(self.document)
        service = ChunkService(self.repository, self.vector_repository)
        service.generate(self.document.id, with_metadata=False)
        document = self.repository.get(self.document.id)
        chunk = document.chunks[0]
        self.vector_repository.save(chunk.id, "test", chunk.content_hash, [0.1, 0.2])
        chunk.embedding_status = "ready"
        chunk.embedded_content_hash = chunk.content_hash
        document.vector_status = "ready"
        self.repository.save(document)

        service.update(self.document.id, chunk.id, {
            "title": "Nouveau titre", "summary": "", "category": "",
            "tags": "contrat", "keywords": "", "text": chunk.text,
        })
        updated = self.repository.get(self.document.id)
        self.assertEqual(updated.chunks[0].embedding_status, "outdated")
        self.assertEqual(updated.vector_status, "outdated")

    def test_split_marks_provenance_approximate(self):
        self.repository.save(self.document)
        service = ChunkService(self.repository, self.vector_repository)
        service.generate(self.document.id, with_metadata=False)
        document = self.repository.get(self.document.id)
        chunk = document.chunks[0]
        service.split(self.document.id, chunk.id, len(chunk.text) // 2)
        updated = self.repository.get(self.document.id)
        self.assertEqual(len(updated.chunks), 2)
        self.assertTrue(all(item.provenance_status == "approximate" for item in updated.chunks))

    def test_sqlite_vector_search_orders_by_cosine_similarity(self):
        self.repository.save(self.document)
        service = ChunkService(self.repository, self.vector_repository)
        service.generate(self.document.id, with_metadata=False)
        chunk = self.repository.get(self.document.id).chunks[0]
        self.vector_repository.save(chunk.id, "test", chunk.content_hash, [1.0, 0.0])
        results = self.vector_repository.search([0.9, 0.1], limit=3)
        self.assertEqual(results[0]["chunk_id"], chunk.id)
        self.assertGreater(results[0]["score"], 0.9)


class TextPreprocessingTest(unittest.TestCase):
    def test_common_pdf_artifacts_are_cleaned_without_mutating_input(self):
        texts = [
            "CONFIDENTIEL\n\uf02aUn para-\ngraphe.\n\n1\nPied commun",
            "CONFIDENTIEL\nDeuxième  texte.\n\n2\nPied commun",
        ]
        result = TextPreprocessingService().process(
            texts, ["symbols", "headers", "page_numbers", "dehyphenate", "spaces"]
        )
        self.assertEqual(texts[0], "CONFIDENTIEL\n\uf02aUn para-\ngraphe.\n\n1\nPied commun")
        self.assertIn("Un paragraphe.", result.texts[0])
        self.assertIn("•Un paragraphe.", result.texts[0])
        self.assertNotIn("CONFIDENTIEL", result.texts[0])
        self.assertNotIn("Pied commun", result.texts[0])
        self.assertEqual(result.changed_pages, 2)


if __name__ == "__main__":
    unittest.main()
