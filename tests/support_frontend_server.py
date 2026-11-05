"""Servidor efímero para probar los adaptadores React por HTTP, con PDF sintético."""
import base64
import json
import os
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf
import uvicorn
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings


if __name__ == '__main__':
    with TemporaryDirectory(prefix='municipal-contract-') as temporary:
        root = Path(temporary)
        settings = Settings(database_url=f"sqlite:///{root / 'test.sqlite'}", storage_dir=str(root / 'pdf'),
                            reviewer_token=os.environ['CONTRACT_TOKEN'], reviewer_id='evaluador-sintetico',
                            protect_dossier_routes=True, cors_origins=['https://municipal-test.vercel.app'])
        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((60, 60), 'FORMULARIO UNICO DE TRAMITE\nDNI: 12345678\nSOLICITO: certificado')
            content = base64.b64encode(pdf.tobytes()).decode()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            print(json.dumps({'port': listener.getsockname()[1], 'pdf': content}), flush=True)
            server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level='error'))
            server.run(sockets=[listener])
