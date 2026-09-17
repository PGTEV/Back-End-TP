from pathlib import Path


class LocalFileStorage:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, dossier_id: str, content: bytes) -> None:
        # ID generado por el caso de uso: nunca utiliza la ruta enviada por el cliente.
        with (self.root / f"{dossier_id}.pdf").open("xb") as file:
            file.write(content)

    def delete(self, dossier_id: str) -> None:
        (self.root / f"{dossier_id}.pdf").unlink(missing_ok=True)
