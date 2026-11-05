import pymupdf
from src.domain.errors import InvalidPDF


class LocalPDFSegmenter:
    def split(self, content, pages):
        try:
            with pymupdf.open(stream=content, filetype='pdf') as source, pymupdf.open() as output:
                if not pages or any(p < 1 or p > len(source) for p in pages):
                    raise InvalidPDF('Páginas del segmento fuera del original.')
                for page in pages:
                    output.insert_pdf(source, from_page=page - 1, to_page=page - 1)
                output.set_metadata({})
                return output.tobytes(deflate=True)
        except InvalidPDF:
            raise
        except Exception as error:
            raise InvalidPDF('No se pudo separar el PDF original.') from error
