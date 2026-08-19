import json
import unittest
from unittest.mock import Mock, patch

from services.pinecone_client import PineconeClient
from services.qdrant_client import QdrantClient


class RemoteVectorAdaptersTest(unittest.TestCase):
    RECORD = {"id": "chunk-1", "values": [0.1, 0.2], "metadata": {"text": "Bonjour"}}

    @patch("services.pinecone_client.urllib.request.urlopen")
    def test_pinecone_translates_canonical_record(self, urlopen):
        response = Mock()
        response.read.return_value = b'{"upsertedCount": 1}'
        urlopen.return_value.__enter__.return_value = response
        client = PineconeClient("index.example", "secret", "test-namespace")

        client.upsert([self.RECORD])

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://index.example/vectors/upsert")
        self.assertEqual(request.get_header("Api-key"), "secret")
        self.assertEqual(payload["namespace"], "test-namespace")
        self.assertEqual(payload["vectors"][0]["values"], [0.1, 0.2])

    def test_qdrant_translates_canonical_record(self):
        client = QdrantClient("https://qdrant.example", "chunks")
        client._request = Mock(return_value={})

        client.upsert([self.RECORD])

        payload = client._request.call_args.args[2]
        self.assertEqual(payload["points"][0]["vector"], [0.1, 0.2])
        self.assertEqual(payload["points"][0]["payload"]["text"], "Bonjour")


if __name__ == "__main__":
    unittest.main()
