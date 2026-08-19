from enum import StrEnum


class PagesStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"


class ChunksStatus(StrEnum):
    MISSING = "missing"
    GENERATING = "generating"
    READY = "ready"
    OUTDATED = "outdated"
    ERROR = "error"


class VectorStatus(StrEnum):
    MISSING = "missing"
    PROCESSING = "processing"
    READY = "ready"
    OUTDATED = "outdated"
    PARTIAL = "partial"
    ERROR = "error"


class MetadataStatus(StrEnum):
    PENDING = "pending"
    GENERATED = "generated"
    MANUALLY_EDITED = "manually_edited"
    ERROR = "error"


class EmbeddingStatus(StrEnum):
    MISSING = "missing"
    PROCESSING = "processing"
    READY = "ready"
    OUTDATED = "outdated"
    ERROR = "error"


class ProvenanceStatus(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    MANUAL = "manual"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
