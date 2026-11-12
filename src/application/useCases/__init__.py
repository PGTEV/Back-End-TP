from hashlib import sha256
from uuid import uuid4
from src.domain.classification import classify
from src.domain.entities import Dossier
from src.domain.errors import IllegibleDocument, InvalidPDF, ProcessingUnavailable
from src.domain.ports import DocumentReader, DossierRepository, FileStorage
from src.domain.intake import is_fictional, protect_and_compare


class ProcessDossier:
    def __init__(self, reader: DocumentReader, repository: DossierRepository, storage: FileStorage):
        self.reader, self.repository, self.storage = reader, repository, storage

    def _documents(self, content):
        return [classify(page) for page in self.reader.extract(content)]

    def execute(self, filename: str, content: bytes, academic_owner: str | None = None) -> Dossier:
        if not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
            raise InvalidPDF("Debe cargar un archivo PDF válido.")
        documents = None
        if academic_owner is not None:
            try:
                documents = self._documents(content)
            except (IllegibleDocument, InvalidPDF):
                raise
            except Exception as error:
                raise ProcessingUnavailable("No se pudo completar el procesamiento.") from error
            if not is_fictional(documents):
                raise InvalidPDF("Marque todas las páginas con EXPEDIENTE FICTICIO para la demostración.")
        dossier = Dossier(str(uuid4()), filename, sha256(content).hexdigest(), academic_owner=academic_owner)
        self.storage.save(dossier.id, content)
        try:
            self.repository.save(dossier)
        except Exception:
            self.storage.delete(dossier.id)
            raise
        try:
            dossier.documents = self._documents(content) if documents is None else documents
            dossier.privacy, dossier.consistency = protect_and_compare(dossier.documents)
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
        dossier = self.repository.get(dossier_id)
        if dossier is not None and dossier.documents:
            dossier.privacy, dossier.consistency = protect_and_compare(dossier.documents)
        return dossier
