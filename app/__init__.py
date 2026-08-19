from __future__ import annotations

import os
import logging
import socket
import threading
import time
from pathlib import Path

from flask import Flask
from flask_wtf.csrf import CSRFError, CSRFProtect

from app.config import Config

from repositories import SQLiteActivityRepository, SQLiteDocumentRepository, SQLiteJobRepository, SQLiteVectorRepository
from services.chunk_service import ChunkService
from services.document_service import DocumentService
from services.job_service import JobService
from services.export_service import ExportService
from services.ocr_service import OCRService
from services.search_service import SearchService
from services.openai_page_correction_service import OpenAIPageCorrectionService


def create_app(data_dir: Path | None = None) -> Flask:
    base_dir = Path(__file__).resolve().parent.parent
    is_local_default = data_dir is None
    data_dir = data_dir or base_dir / "data"

    Config.validate()
    app = Flask(__name__, template_folder=str(base_dir / "templates"), static_folder=str(base_dir / "static"))
    app.config.from_object(Config)
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    CSRFProtect(app)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return "Le formulaire a expiré. Rechargez la page et réessayez.", 400

    repository = SQLiteDocumentRepository(data_dir / "ocr_pipe.db")
    vector_repository = SQLiteVectorRepository(data_dir / "ocr_pipe.db")
    job_repository = SQLiteJobRepository(data_dir / "ocr_pipe.db")
    activity_repository = SQLiteActivityRepository(data_dir / "ocr_pipe.db")
    document_service = DocumentService(repository, data_dir)
    chunk_service = ChunkService(repository, vector_repository)
    ocr_service = OCRService(repository)
    correction_service = OpenAIPageCorrectionService(repository)
    job_service = JobService(job_repository, chunk_service, activity_repository, ocr_service,
                             correction_service)
    export_service = ExportService(repository)
    search_service = SearchService(vector_repository)
    if data_dir == base_dir / "data":
        document_service.migrate_json_documents([
            base_dir / "DATA" / "extracted",
            base_dir / "data" / "extracted",
        ])

    app.extensions["repository"] = repository
    app.extensions["document_service"] = document_service
    app.extensions["chunk_service"] = chunk_service
    app.extensions["vector_repository"] = vector_repository
    app.extensions["job_repository"] = job_repository
    app.extensions["job_service"] = job_service
    app.extensions["activity_repository"] = activity_repository
    app.extensions["export_service"] = export_service
    app.extensions["ocr_service"] = ocr_service
    app.extensions["search_service"] = search_service
    app.extensions["correction_service"] = correction_service

    # En usage local, éviter que les jobs restent bloqués si l'utilisateur ne
    # pense pas à lancer un second terminal. Le démarrage au premier HTTP évite
    # les doublons créés par le reloader Flask et ne s'active pas dans les tests.
    if is_local_default and os.environ.get("OCR_PIPE_AUTO_WORKER", "1") == "1":
        worker_started = threading.Event()

        def worker_loop():
            worker_id = f"embedded:{socket.gethostname()}:{os.getpid()}"
            while True:
                if not job_service.run_next(worker_id):
                    time.sleep(0.75)

        @app.before_request
        def ensure_local_worker():
            if not worker_started.is_set():
                worker_started.set()
                threading.Thread(
                    target=worker_loop, name="ocr-pipe-local-worker", daemon=True
                ).start()

    from app.routes.documents import documents
    from app.routes.chunks import chunks
    from app.routes.jobs import jobs
    from app.routes.rag import rag
    app.register_blueprint(documents)
    app.register_blueprint(chunks)
    app.register_blueprint(jobs)
    app.register_blueprint(rag)
    return app
