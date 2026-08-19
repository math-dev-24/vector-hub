from __future__ import annotations

class RemoteVectorPublicationService:
    def __init__(self, documents, vectors, publications, gateway=None, *,
                 destination="remote:default", display_name="Non configuré"):
        self.documents = documents
        self.vectors = vectors
        self.publications = publications
        self.destination = destination
        self.display_name = display_name
        self.gateway = gateway

    @property
    def collection(self) -> str:
        # Compatibilité interne avec les vues existantes.
        return self.destination

    @property
    def configured(self) -> bool:
        return self.gateway is not None

    def publish_document(self, document_id: str, on_progress=None) -> int:
        if not self.gateway:
            raise RuntimeError("Aucune base vectorielle distante n'est configurée.")
        document = self.documents.get(document_id)
        targets = []
        for chunk in document.chunks:
            vector = self.vectors.get(chunk.id)
            if chunk.embedding_status != "ready" or vector is None:
                continue
            if self.publications.get_input_hash(chunk.id, self.destination) == vector["input_hash"]:
                continue
            targets.append((chunk, vector))
        if not targets:
            return 0
        self.gateway.ensure_target(targets[0][1]["dimensions"])
        completed = 0
        for offset in range(0, len(targets), 50):
            batch = targets[offset:offset + 50]
            records = [{
                "id": chunk.id,
                "values": vector["embedding"],
                "metadata": {
                    "chunk_id": chunk.id, "document_id": document.id,
                    "filename": document.filename, "position": chunk.position,
                    "text": chunk.text, "title": chunk.title, "summary": chunk.summary,
                    "category": chunk.category, "tags": chunk.tags,
                    "keywords": chunk.keywords,
                    "source_pages": [str(source.page_number) for source in chunk.sources],
                    "provenance": str(chunk.provenance_status),
                    "input_hash": vector["input_hash"], "embedding_model": vector["model"],
                },
            } for chunk, vector in batch]
            try:
                self.gateway.upsert(records)
            except Exception as error:
                for chunk, vector in batch:
                    self.publications.mark_error(
                        chunk.id, self.destination, vector["input_hash"], str(error)
                    )
                raise
            for chunk, vector in batch:
                self.publications.mark_published(chunk.id, self.destination, vector["input_hash"])
                completed += 1
                if on_progress:
                    on_progress(completed, len(targets), f"publication {self.display_name}")
        return completed
