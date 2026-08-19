from __future__ import annotations

import json
import urllib.error
import urllib.request


class QdrantClient:
    """Adaptateur Qdrant du port RemoteVectorGateway."""
    def __init__(self, url: str, collection: str, api_key: str = ""):
        self.url = url.rstrip("/")
        self.collection = collection
        self.api_key = api_key

    def ensure_target(self, dimensions: int) -> None:
        try:
            self._request("GET", f"/collections/{self.collection}")
        except RuntimeError as error:
            if "HTTP 404" not in str(error):
                raise
            self._request("PUT", f"/collections/{self.collection}", {
                "vectors": {"size": dimensions, "distance": "Cosine"}
            })

    def upsert(self, records: list[dict]) -> None:
        points = [{
            "id": record["id"], "vector": record["values"],
            "payload": record["metadata"],
        } for record in records]
        self._request(
            "PUT", f"/collections/{self.collection}/points?wait=true", {"points": points}
        )

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        request = urllib.request.Request(self.url + path, body, headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Qdrant HTTP {error.code}") from error
        except urllib.error.URLError as error:
            raise RuntimeError("Qdrant est inaccessible") from error
