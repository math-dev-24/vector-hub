from __future__ import annotations

from typing import Protocol


class RemoteVectorGateway(Protocol):
    """Port sortant utilisé par le métier, indépendant du fournisseur."""

    def ensure_target(self, dimensions: int) -> None: ...
    def upsert(self, records: list[dict]) -> None: ...

