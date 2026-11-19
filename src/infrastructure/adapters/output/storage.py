from pathlib import Path
import os
from uuid import UUID
from src.domain.errors import ProcessingUnavailable

MAGIC = b'OWASP-PDF-v1\n'

class LocalFileStorage:
    """Optional authenticated encryption; legacy PDFs are not migrated implicitly."""
    def __init__(self, root: str, encrypt=False, keys=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.encrypt = encrypt
        self.cipher = None
        if keys:
            from cryptography.fernet import Fernet, MultiFernet
            self.cipher = MultiFernet([Fernet(key.encode()) for key in keys])
        if encrypt and self.cipher is None:
            raise ValueError('El cifrado de originales requiere una clave válida.')

    def _path(self, dossier_id, encrypted=False):
        identifier = str(UUID(dossier_id))
        return self.root / (identifier + ('.pdf.enc' if encrypted else '.pdf'))

    def save(self, dossier_id: str, content: bytes) -> None:
        plain, encrypted = self._path(dossier_id), self._path(dossier_id, True)
        if plain.exists() or encrypted.exists():
            raise FileExistsError('El original ya existe.')
        path = encrypted if self.encrypt else plain
        payload = MAGIC + self.cipher.encrypt(str(UUID(dossier_id)).encode() + b'\n' + content) if self.encrypt else content
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as file:
                file.write(payload)
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def delete(self, dossier_id: str) -> None:
        self._path(dossier_id).unlink(missing_ok=True)
        self._path(dossier_id, True).unlink(missing_ok=True)

    def read(self, dossier_id: str) -> bytes | None:
        encrypted = self._path(dossier_id, True)
        if encrypted.exists():
            if self.cipher is None:
                raise ProcessingUnavailable('No está disponible la clave del original cifrado.')
            from cryptography.fernet import InvalidToken
            payload = encrypted.read_bytes()
            if not payload.startswith(MAGIC):
                raise ProcessingUnavailable('Formato de original cifrado no reconocido.')
            try:
                decrypted = self.cipher.decrypt(payload[len(MAGIC):])
                prefix = str(UUID(dossier_id)).encode() + b'\n'
                if not decrypted.startswith(prefix):
                    raise ProcessingUnavailable('El original cifrado pertenece a otro expediente.')
                return decrypted[len(prefix):]
            except InvalidToken as error:
                raise ProcessingUnavailable('No se pudo verificar el original cifrado.') from error
        try:
            return self._path(dossier_id).read_bytes()
        except FileNotFoundError:
            return None
