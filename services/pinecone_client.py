from __future__ import annotations

import json
import urllib.error
import urllib.request


class PineconeClient:
    """Adaptateur Pinecone BYOV du port RemoteVectorGateway."""

    def __init__(self, index_host: str, api_key: str, namespace: str = ""):
        host = index_host.strip().rstrip("/")
        self.index_host = host if host.startswith(("http://", "https://")) else f"https://{host}"
        self.api_key = api_key
        self.namespace = namespace

    def ensure_target(self, dimensions: int) -> None:
        # L'index Pinecone est provisionné en amont. Pinecone valide la dimension
        # des vecteurs pendant l'upsert.
        return None

    def upsert(self, records: list[dict]) -> None:
        payload = {
            "vectors": [{
                "id": record["id"], "values": record["values"],
                "metadata": record["metadata"],
            } for record in records]
        }
        if self.namespace:
            payload["namespace"] = self.namespace
        self._request("POST", "/vectors/upsert", payload)

    def _request(self, method: str, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self.index_host + path, json.dumps(payload).encode(), {
                "Api-Key": self.api_key,
                "Content-Type": "application/json",
                "X-Pinecone-Api-Version": "2026-04",
            }, method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Pinecone HTTP {error.code}") from error
        except urllib.error.URLError as error:
            raise RuntimeError("Pinecone est inaccessible") from error
