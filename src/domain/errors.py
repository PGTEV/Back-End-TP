class InvalidPDF(Exception):
    pass


class IllegibleDocument(Exception):
    message = "Documento ilegible, por favor vuelva a cargar el archivo"

    def __init__(self, page: int):
        self.page = page
        self.dossier_id = None
        super().__init__(self.message)


class ProcessingUnavailable(Exception):
    pass
