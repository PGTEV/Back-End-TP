from typing import Protocol
from src.domain.entities import Dossier
from src.domain.valueObjects import Page


class DocumentReader(Protocol):
    def extract(self, content: bytes) -> list[Page]: ...


class DossierRepository(Protocol):
    def save(self, dossier: Dossier) -> None: ...
    def get(self, dossier_id: str) -> Dossier | None: ...


class FileStorage(Protocol):
    def save(self, dossier_id: str, content: bytes) -> None: ...
    def delete(self, dossier_id: str) -> None: ...
