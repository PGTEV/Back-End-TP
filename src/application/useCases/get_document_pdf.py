from hashlib import sha256
from src.domain.errors import DocumentNotFound, InvalidPDF, ProcessingUnavailable
from src.domain.ports import DossierRepository, FileStorage, PDFSegmenter


class GetDocumentPDF:
    def __init__(self, repository: DossierRepository, storage: FileStorage, segmenter: PDFSegmenter):
        self.repository, self.storage, self.segmenter = repository, storage, segmenter

    def execute(self, dossier_id: str, index: int):
        dossier = self.repository.get(dossier_id)
        if dossier is None or index < 0 or index >= len(dossier.documents):
            raise DocumentNotFound('Segmento no encontrado.')
        try:
            content = self.storage.read(dossier.id)
            if content is None:
                raise DocumentNotFound('El PDF original no está disponible en el almacenamiento.')
            if sha256(content).hexdigest() != dossier.sha256:
                raise ProcessingUnavailable('La integridad del PDF original no pudo verificarse.')
            return self.segmenter.split(content, dossier.documents[index].pages)
        except (OSError, InvalidPDF) as error:
            raise ProcessingUnavailable('No se pudo recuperar el segmento del original.') from error
