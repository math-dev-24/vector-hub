from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from database import run_migrations
from models.document_model import ChunkModel, ChunkSourceModel, DocumentInfo, DocumentModel, PageModel, utc_now


class SQLiteDocumentRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        run_migrations(self.database_path)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list(self) -> list[DocumentInfo]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT d.*,
                       (SELECT COUNT(*) FROM pages p WHERE p.document_id = d.id) AS pages_count,
                       (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunks_count
                FROM documents d
                ORDER BY d.updated_at DESC
            """).fetchall()
        return [DocumentInfo(
            id=row["id"], filename=row["filename"], pages_count=row["pages_count"],
            chunks_count=row["chunks_count"], pages_status=row["pages_status"],
            chunks_status=row["chunks_status"], vector_status=row["vector_status"],
            updated_at=row["updated_at"],
        ) for row in rows]

    def get(self, document_id: str) -> DocumentModel:
        with self._connect() as connection:
            document_row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
            if document_row is None:
                raise KeyError(document_id)
            page_rows = connection.execute(
                "SELECT * FROM pages WHERE document_id = ? ORDER BY position", (document_id,)
            ).fetchall()
            chunk_rows = connection.execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY position", (document_id,)
            ).fetchall()
        return DocumentModel(
            id=document_row["id"], filename=document_row["filename"],
            original_path=document_row["original_path"], pages_status=document_row["pages_status"],
            chunks_status=document_row["chunks_status"], vector_status=document_row["vector_status"],
            version=document_row["version"],
            created_at=document_row["created_at"], updated_at=document_row["updated_at"],
            pages=[PageModel(
                id=row["id"], page=row["page_number"], position=row["position"],
                original_text=row["original_text"], corrected_text=row["corrected_text"], status=row["status"],
                extraction_method=row["extraction_method"], ocr_status=row["ocr_status"]
            ) for row in page_rows],
            chunks=[self._row_to_chunk(row) for row in chunk_rows],
        )

    def save(self, document: DocumentModel) -> None:
        now = utc_now().isoformat()
        document.updated_at = datetime.fromisoformat(now)
        with self._connect() as connection:
            current = connection.execute(
                "SELECT version FROM documents WHERE id = ?", (document.id,)
            ).fetchone()
            if current is None:
                connection.execute("""INSERT INTO documents
                    (id, filename, original_path, pages_status, chunks_status, vector_status,
                     created_at, updated_at, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (document.id, document.filename, document.original_path, document.pages_status,
                     document.chunks_status, document.vector_status, document.created_at.isoformat(), now))
                document.version = 0
            else:
                if current["version"] != document.version:
                    raise RuntimeError("Le document a été modifié par une autre opération.")
                document.version += 1
                connection.execute("""UPDATE documents SET filename=?, original_path=?, pages_status=?,
                    chunks_status=?, vector_status=?, updated_at=?, version=? WHERE id=?""",
                    (document.filename, document.original_path, document.pages_status,
                     document.chunks_status, document.vector_status, now, document.version, document.id))
            connection.execute("DELETE FROM pages WHERE document_id = ?", (document.id,))
            connection.executemany("""INSERT INTO pages
                (id, document_id, page_number, position, original_text, corrected_text, status,
                 extraction_method, ocr_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(page.id, document.id, page.page, page.position, page.original_text,
                  page.corrected_text, page.status, page.extraction_method, page.ocr_status)
                 for page in document.pages])
            preserved_embeddings = connection.execute("""SELECT e.* FROM chunk_embeddings e
                JOIN chunks c ON c.id=e.chunk_id WHERE c.document_id=?""", (document.id,)).fetchall()
            connection.execute("DELETE FROM chunks WHERE document_id = ?", (document.id,))
            connection.executemany("""INSERT INTO chunks
                (id, document_id, position, text, title, summary, category, tags_json,
                 keywords_json, section_path_json, sources_json, token_count, content_hash,
                 metadata_status, manually_reviewed, embedding_status, embedded_content_hash,
                 created_at, updated_at, metadata_model, metadata_prompt_version, title_source,
                 summary_source, category_source, tags_source, provenance_status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [self._chunk_values(chunk) for chunk in document.chunks])
            retained_chunk_ids = {chunk.id for chunk in document.chunks}
            connection.executemany("""INSERT INTO chunk_embeddings
                (chunk_id, model, input_hash, dimensions, embedding_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [(row["chunk_id"], row["model"], row["input_hash"], row["dimensions"],
                  row["embedding_json"], row["created_at"], row["updated_at"])
                 for row in preserved_embeddings if row["chunk_id"] in retained_chunk_ids])

    def update_page(self, document_id: str, page: PageModel) -> None:
        with self._connect() as connection:
            connection.execute("""UPDATE pages SET original_text=?, corrected_text=?, status=?,
                extraction_method=?, ocr_status=?
                WHERE id=? AND document_id=?""",
                (page.original_text, page.corrected_text, page.status, page.extraction_method,
                 page.ocr_status, page.id, document_id))
            self._touch(connection, document_id)

    def save_pages(self, document_id: str, pages: list[PageModel], *, expected_version: int,
                   delete_page_id: str | None = None, has_chunks: bool = False) -> bool:
        with self._connect() as connection:
            self._assert_version(connection, document_id, expected_version)
            connection.executemany(
                """UPDATE pages SET corrected_text=?, status=?, extraction_method=?, ocr_status=?
                   WHERE id=? AND document_id=?""",
                [(page.corrected_text, page.status, page.extraction_method, page.ocr_status,
                  page.id, document_id) for page in pages],
            )
            deleted = True
            if delete_page_id:
                result = connection.execute(
                    "DELETE FROM pages WHERE id=? AND document_id=?", (delete_page_id, document_id)
                )
                deleted = result.rowcount > 0
                self._resequence(connection, "pages", document_id)
            connection.execute("""UPDATE documents SET pages_status='reviewed',
                chunks_status=CASE WHEN ? THEN 'outdated' ELSE chunks_status END,
                vector_status=CASE WHEN ? THEN 'outdated' ELSE vector_status END,
                updated_at=?, version=version+1 WHERE id=?""",
                (int(has_chunks), int(has_chunks), utc_now().isoformat(), document_id))
            return deleted

    def delete_page(self, document_id: str, page_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM pages WHERE id=? AND document_id=?", (page_id, document_id)
            )
            self._resequence(connection, "pages", document_id)
            self._touch(connection, document_id)
            return result.rowcount > 0

    def replace_chunks(self, document_id: str, chunks: list[ChunkModel]) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
            connection.executemany("""INSERT INTO chunks
                (id, document_id, position, text, title, summary, category, tags_json,
                 keywords_json, section_path_json, sources_json, token_count, content_hash,
                 metadata_status, manually_reviewed, embedding_status, embedded_content_hash,
                 created_at, updated_at, metadata_model, metadata_prompt_version, title_source,
                 summary_source, category_source, tags_source, provenance_status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [self._chunk_values(chunk) for chunk in chunks])
            self._touch(connection, document_id)

    def update_chunk(self, chunk: ChunkModel, expected_version: int | None = None) -> None:
        values = self._chunk_values(chunk)
        with self._connect() as connection:
            if expected_version is not None:
                self._assert_version(connection, chunk.document_id, expected_version)
            connection.execute("""UPDATE chunks SET position=?, text=?, title=?, summary=?, category=?,
                tags_json=?, keywords_json=?, section_path_json=?, sources_json=?, token_count=?,
                content_hash=?, metadata_status=?, manually_reviewed=?, embedding_status=?,
                embedded_content_hash=?, updated_at=?, metadata_model=?, metadata_prompt_version=?,
                title_source=?, summary_source=?, category_source=?, tags_source=?, provenance_status=?
                WHERE id=? AND document_id=?""",
                (values[2], *values[3:17], values[18], *values[19:], chunk.id, chunk.document_id))
            self._touch(connection, chunk.document_id)

    def delete_chunk(self, document_id: str, chunk_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM chunks WHERE id=? AND document_id=?", (chunk_id, document_id)
            )
            self._resequence(connection, "chunks", document_id)
            self._touch(connection, document_id)
            return result.rowcount > 0

    def insert_chunk(self, chunk: ChunkModel) -> None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, position FROM chunks WHERE document_id=? AND position>=? ORDER BY position DESC",
                (chunk.document_id, chunk.position),
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE chunks SET position=? WHERE id=?", (row["position"] + 1, row["id"])
                )
            connection.execute("""INSERT INTO chunks
                (id, document_id, position, text, title, summary, category, tags_json,
                 keywords_json, section_path_json, sources_json, token_count, content_hash,
                 metadata_status, manually_reviewed, embedding_status, embedded_content_hash,
                 created_at, updated_at, metadata_model, metadata_prompt_version, title_source,
                 summary_source, category_source, tags_source, provenance_status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._chunk_values(chunk))
            self._touch(connection, chunk.document_id)

    def update_statuses(self, document_id: str, *, pages_status=None, chunks_status=None, vector_status=None) -> None:
        updates, values = [], []
        for column, value in (("pages_status", pages_status), ("chunks_status", chunks_status),
                              ("vector_status", vector_status)):
            if value is not None:
                updates.append(f"{column}=?")
                values.append(value)
        if not updates:
            return
        with self._connect() as connection:
            connection.execute(
                f"UPDATE documents SET {', '.join(updates)}, updated_at=?, version=version+1 WHERE id=?",
                (*values, utc_now().isoformat(), document_id),
            )

    def delete(self, document_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    @staticmethod
    def _chunk_values(chunk: ChunkModel) -> tuple:
        return (
            chunk.id, chunk.document_id, chunk.position, chunk.text, chunk.title, chunk.summary,
            chunk.category, json.dumps(chunk.tags, ensure_ascii=False),
            json.dumps(chunk.keywords, ensure_ascii=False), json.dumps(chunk.section_path, ensure_ascii=False),
            json.dumps([source.model_dump() for source in chunk.sources], ensure_ascii=False),
            chunk.token_count, chunk.content_hash, chunk.metadata_status, int(chunk.manually_reviewed),
            chunk.embedding_status, chunk.embedded_content_hash, chunk.created_at.isoformat(),
            chunk.updated_at.isoformat(), chunk.metadata_model, chunk.metadata_prompt_version,
            chunk.title_source, chunk.summary_source, chunk.category_source, chunk.tags_source,
            chunk.provenance_status,
        )

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> ChunkModel:
        return ChunkModel(
            id=row["id"], document_id=row["document_id"], position=row["position"], text=row["text"],
            title=row["title"], summary=row["summary"], category=row["category"],
            tags=json.loads(row["tags_json"]), keywords=json.loads(row["keywords_json"]),
            section_path=json.loads(row["section_path_json"]),
            sources=[ChunkSourceModel.model_validate(item) for item in json.loads(row["sources_json"])],
            token_count=row["token_count"], content_hash=row["content_hash"],
            metadata_status=row["metadata_status"], manually_reviewed=bool(row["manually_reviewed"]),
            embedding_status=row["embedding_status"], embedded_content_hash=row["embedded_content_hash"],
            metadata_model=row["metadata_model"], metadata_prompt_version=row["metadata_prompt_version"],
            title_source=row["title_source"], summary_source=row["summary_source"],
            category_source=row["category_source"], tags_source=row["tags_source"],
            provenance_status=row["provenance_status"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _touch(connection: sqlite3.Connection, document_id: str) -> None:
        connection.execute(
            "UPDATE documents SET updated_at=?, version=version+1 WHERE id=?",
            (utc_now().isoformat(), document_id),
        )

    @staticmethod
    def _assert_version(connection: sqlite3.Connection, document_id: str, expected_version: int) -> None:
        row = connection.execute(
            "SELECT version FROM documents WHERE id=?", (document_id,)
        ).fetchone()
        if row is None:
            raise KeyError(document_id)
        if row["version"] != expected_version:
            raise RuntimeError("Le document a été modifié ailleurs. Rechargez la page.")

    @staticmethod
    def _resequence(connection: sqlite3.Connection, table: str, document_id: str) -> None:
        rows = connection.execute(
            f"SELECT id FROM {table} WHERE document_id=? ORDER BY position", (document_id,)
        ).fetchall()
        for position, row in enumerate(rows):
            connection.execute(f"UPDATE {table} SET position=? WHERE id=?", (-(position + 1), row["id"]))
        for position, row in enumerate(rows):
            connection.execute(f"UPDATE {table} SET position=? WHERE id=?", (position, row["id"]))
