"""Verifica el PDF fuente sin modificarlo ni copiarlo al repositorio."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import pymupdf


def verify(path):
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / 'config/tupa_huancayo.json').read_text(encoding='utf-8'))
    path = Path(path)
    fingerprint = sha256(path.read_bytes()).hexdigest()
    if fingerprint != catalog['source_sha256']:
        raise ValueError('El PDF no coincide con la fuente del catálogo; requiere nueva revisión.')
    with pymupdf.open(path) as pdf:
        records = []
        for procedure in catalog['procedures']:
            text = '\n'.join(pdf[n - 1].get_text() for n in procedure['pdf_pages'])
            if procedure['code'] not in text:
                raise ValueError('No se encontró el código en sus páginas fuente: ' + procedure['code'])
            records.append({'codigo': procedure['code'], 'paginas_pdf': procedure['pdf_pages'],
                            'requisitos_piloto': len(procedure['requirements'])})
        return {'archivo': path.name, 'sha256': fingerprint, 'paginas': len(pdf),
                'ordenanza_observada_en_portada': '790-MPH/CM',
                'revision_visual': 'Portada y páginas PDF 75, 76, 80, 81 y 524 verificadas',
                'catalogo_completo': False, 'vigencia_2026_certificada': False, 'procedimientos': records}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf')
    parser.add_argument('--output', default='config/tupa_source_verification.json')
    args = parser.parse_args()
    Path(args.output).write_text(json.dumps(verify(args.pdf), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Fuente verificada; no se modificó el PDF original.')
