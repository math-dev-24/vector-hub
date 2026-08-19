from __future__ import annotations

import os


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024
    MAX_PDF_PAGES = int(os.environ.get("MAX_PDF_PAGES", "500"))
    MAX_FILES_PER_UPLOAD = int(os.environ.get("MAX_FILES_PER_UPLOAD", "20"))
    OCR_LANGUAGE = os.environ.get("OCR_LANGUAGE", "fra+eng")
    OCR_DPI = int(os.environ.get("OCR_DPI", "300"))
    WTF_CSRF_TIME_LIMIT = 3600

    @classmethod
    def validate(cls) -> None:
        if os.environ.get("FLASK_ENV") == "production" and cls.SECRET_KEY == "dev-secret-key":
            raise RuntimeError("FLASK_SECRET_KEY doit être configurée en production.")
