from hashlib import sha256
from uuid import uuid4
from src.domain.classification import classify
from src.domain.entities import Dossier
from src.domain.errors import IllegibleDocument, InvalidPDF, ProcessingUnavailable
from src.domain.ports import DocumentReader, DossierRepository, FileStorage


class ProcessDossier:
    def __init__(self, reader: DocumentReader, repository: DossierRepository, storage: FileStorage):
        self.reader, self.repository, self.storage = reader, repository, storage

    def execute(self, filename: str, content: bytes) -> Dossier:
        if not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
            raise InvalidPDF("Debe cargar un archivo PDF válido.")
        dossier = Dossier(str(uuid4()), filename, sha256(content).hexdigest())
        self.storage.save(dossier.id, content)
        try:
            self.repository.save(dossier)
        except Exception:
            self.storage.delete(dossier.id)
            raise
        try:
            pages = self.reader.extract(content)
            dossier.documents = [classify(page) for page in pages]
            dossier.status = "PROCESADO"
        except IllegibleDocument as error:
            dossier.status, dossier.error = "ILEGIBLE", error.message
            self.repository.save(dossier)
            error.dossier_id = dossier.id
            raise
        except InvalidPDF as error:
            dossier.status, dossier.error = "INVALIDO", str(error)
            self.repository.save(dossier)
            raise
        except Exception as error:
            dossier.status, dossier.error = "ERROR", "No se pudo completar el procesamiento."
            self.repository.save(dossier)
            raise ProcessingUnavailable(dossier.error) from error
        self.repository.save(dossier)
        return dossier


class GetDossier:
    def __init__(self, repository: DossierRepository):
        self.repository = repository

    def execute(self, dossier_id: str) -> Dossier | None:
        return self.repository.get(dossier_id)
