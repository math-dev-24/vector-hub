import os
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from models.document_model import ChunkModel, DocumentModel, PageModel
from repositories import (SQLiteActivityRepository, SQLiteDocumentRepository, SQLiteJobRepository,
                          SQLiteRemotePublicationRepository, SQLiteVectorRepository)
from services.job_service import JobService
from services.openai_metadata_service import GeneratedChunkMetadata, OpenAIMetadataService
from services.vectorization_service import VectorizationService
from services.openai_page_correction_service import CorrectedPage, OpenAIPageCorrectionService
from services.remote_vector_publication_service import RemoteVectorPublicationService


class MetadataServiceTest(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test"})
    def test_structured_metadata_and_manual_preservation(self):
        service = OpenAIMetadataService()
        metadata = GeneratedChunkMetadata(
            title="Titre IA", summary="Résumé IA", category="contrat",
            tags=["juridique"], keywords=["accord"],
        )
        service.client = SimpleNamespace(
            responses=SimpleNamespace(parse=Mock(return_value=SimpleNamespace(output_parsed=metadata)))
        )
        chunk = ChunkModel(
            id=str(uuid.uuid4()), document_id=str(uuid.uuid4()), position=0,
            text="Texte", title="Titre manuel", title_source="manual",
        )
        service.enrich([chunk])
        self.assertEqual(chunk.title, "Titre manuel")
        self.assertEqual(chunk.summary, "Résumé IA")
        self.assertEqual(chunk.metadata_prompt_version, "metadata-v2")

    def test_embedding_hash_includes_metadata(self):
        chunk = ChunkModel(id="c", document_id="d", position=0, text="Texte", title="A")
        first = VectorizationService.embedding_input_hash(chunk)
        chunk.title = "B"
        self.assertNotEqual(first, VectorizationService.embedding_input_hash(chunk))

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test"})
    def test_page_correction_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteDocumentRepository(Path(directory) / "pages.db")
            page = PageModel(id="p1", page=1, position=0, original_text="Tex-\nte original",
                             corrected_text="Tex-\nte original")
            repository.save(DocumentModel(id="d1", filename="test.pdf", pages=[page]))
            service = OpenAIPageCorrectionService(repository)
            service.client = SimpleNamespace(responses=SimpleNamespace(parse=Mock(
                return_value=SimpleNamespace(output_parsed=CorrectedPage(
                    corrected_text="Texte original", notes=[]
                ))
            )))
            result = service.correct_page("d1", "p1", expected_text="Tex-\nte original")
            saved = repository.get("d1").pages[0]
            self.assertTrue(result["updated"])
            self.assertEqual(saved.original_text, "Tex-\nte original")
            self.assertEqual(saved.corrected_text, "Texte original")
            self.assertEqual(saved.status, "ai_corrected")


class JobServiceTest(unittest.TestCase):
    def test_job_is_persisted_and_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "jobs.db"
            jobs = SQLiteJobRepository(database_path)
            activity = SQLiteActivityRepository(database_path)
            chunks = Mock()
            chunks.generate.return_value = 3
            service = JobService(jobs, chunks, activity)
            job = service.enqueue("generate_document")
            self.assertEqual(jobs.get(job.id).status, "pending")
            self.assertTrue(service.run_next("test-worker"))
            saved = jobs.get(job.id)
            self.assertEqual(saved.status, "completed")
            self.assertEqual(saved.worker_id, "test-worker")
            self.assertEqual(saved.payload["result"]["chunks"], 3)
            self.assertGreaterEqual(len(activity.list_recent()), 3)

    def test_pending_job_can_be_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "jobs.db"
            jobs = SQLiteJobRepository(database_path)
            service = JobService(jobs, Mock(), SQLiteActivityRepository(database_path))
            job = service.enqueue("generate_all")
            self.assertTrue(service.cancel(job.id))
            self.assertEqual(jobs.get(job.id).status, "cancelled")
            self.assertFalse(service.run_next("test-worker"))


class RemoteVectorPublicationServiceTest(unittest.TestCase):
    def test_publishes_ready_chunks_and_skips_unchanged_vectors(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "publish.db"
            documents = SQLiteDocumentRepository(database_path)
            vectors = SQLiteVectorRepository(database_path)
            publications = SQLiteRemotePublicationRepository(database_path)
            chunk = ChunkModel(
                id=str(uuid.uuid4()), document_id="d1", position=0, text="Texte propre",
                embedding_status="ready",
            )
            documents.save(DocumentModel(id="d1", filename="test.pdf", chunks=[chunk]))
            vectors.save(chunk.id, "embedding-test", "hash-1", [0.1, 0.2])
            client = Mock()
            service = RemoteVectorPublicationService(documents, vectors, publications, client)

            self.assertEqual(service.publish_document("d1"), 1)
            self.assertEqual(service.publish_document("d1"), 0)
            client.ensure_target.assert_called_once_with(2)
            client.upsert.assert_called_once()
            point = client.upsert.call_args.args[0][0]
            self.assertEqual(point["id"], chunk.id)
            self.assertEqual(point["metadata"]["text"], "Texte propre")
            self.assertEqual(publications.summary("d1", service.collection)["published"], 1)


if __name__ == "__main__":
    unittest.main()
