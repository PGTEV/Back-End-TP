"""Registros sintéticos por HTTP ASGI local. Sin .env, nube ni inferencias remotas.

python -m scripts.batch_demo_records --count 500 --output data/evaluacion-500
"""
import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from math import ceil
import platform
from pathlib import Path
import secrets
import sqlite3
from statistics import median
from time import perf_counter
from fastapi.testclient import TestClient
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings
from scripts.academic_examples import demo_pdf

CODES = ('PA12115285', 'PA121121B0', 'PE1027344C1')


def case_spec(index):
    profile = index % 10
    code = CODES[index % len(CODES)]
    if profile < 4:
        return code, 'CONFORME', 'CONFORME', {}
    if profile < 6:
        return code, 'FALTA_PAGO', 'OBSERVADO', {'missing': 'pago'}
    if profile < 8:
        return code, 'DNI_DIFERENTE', 'PENDIENTE_REVISION', {'dni_conflict': True}
    if profile == 8:
        return 'PA12115285', 'PLANO_SIN_FIRMA_FICTICIA', 'OBSERVADO', {'unsigned': True}
    return code, 'ASUNTO_AMBIGUO', 'CONFORME', {'ambiguous': True}


def timings(values):
    ordered = sorted(values)
    return {'mediana_ms': round(median(ordered), 3),
            'p95_ms_rango_mas_cercano': round(ordered[ceil(.95 * len(ordered)) - 1], 3),
            'min_ms': round(ordered[0], 3), 'max_ms': round(ordered[-1], 3)}


def write_csv(path, fieldnames, rows):
    with path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_batch(output, count=500, progress=True):
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError('La cantidad debe estar entre 1 y 1000 expedientes.')
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('La carpeta de salida debe ser nueva o estar vacía; no se sobrescriben datos.')
    output.mkdir(parents=True, exist_ok=True)
    database = output / 'evaluacion.sqlite'
    storage = output / 'originales'
    # No admite DATABASE_URL ni lee .env. Solo se crea una base SQLite del lote.
    token = secrets.token_urlsafe(40)
    settings = Settings(_env_file=None, database_url='sqlite:///' + database.as_posix(),
                        storage_dir=str(storage), academic_demo=True, protect_dossier_routes=True,
                        reviewer_id='evaluador-lote-ficticio', reviewer_token=token,
                        ai_provider='none', openai_enabled=False, gemini_enabled=False)
    headers = {'Authorization': 'Bearer ' + token}
    rows, upload_ms, validation_ms, cases_ms = [], [], [], []
    started = perf_counter()
    with TestClient(create_app(settings)) as client:
        for index in range(count):
            reference = f'LOTE-{index + 1:06d}'
            code, scenario, expected, options = case_spec(index)
            content = demo_pdf(code, reference=reference, dni=f'{index + 1000:08d}', **options)
            filename = reference + '-FICTICIO.pdf'
            case_started = perf_counter()
            response = client.post('/api/expedientes', headers=headers,
                                   files={'archivo': (filename, content, 'application/pdf')})
            upload_elapsed = (perf_counter() - case_started) * 1000
            if response.status_code != 201:
                raise RuntimeError(f'{reference}: carga fallida, HTTP {response.status_code}.')
            dossier = response.json()
            if dossier['estado'] != 'PROCESADO' or dossier['sha256'] != sha256(content).hexdigest():
                raise RuntimeError(f'{reference}: carga no verificable.')
            route = '/api/expedientes/' + dossier['id']
            validation_started = perf_counter()
            response = client.post(route + '/validacion', headers=headers,
                                   json={'codigo_tupa': code, 'revision': 0, 'verificaciones': {}})
            validation_elapsed = (perf_counter() - validation_started) * 1000
            if response.status_code != 200:
                raise RuntimeError(f'{reference}: validación fallida, HTTP {response.status_code}.')
            flow = response.json()
            if flow['validation']['estado'] != expected:
                raise RuntimeError(f'{reference}: resultado académico diferente del esperado.')
            if expected == 'CONFORME':
                response = client.post(route + '/enrutamiento', headers=headers, json={'revision': flow['revision']})
                if response.status_code != 200:
                    raise RuntimeError(f'{reference}: enrutamiento fallido, HTTP {response.status_code}.')
                flow = response.json()
                if scenario == 'ASUNTO_AMBIGUO' and flow['routing']['estado'] != 'CLASIFICACION_MANUAL':
                    raise RuntimeError(f'{reference}: el asunto ambiguo requiere clasificación manual.')
            queried = client.get(route, headers=headers)
            if queried.status_code != 200 or queried.json()['sha256'] != dossier['sha256']:
                raise RuntimeError(f'{reference}: no se recuperó el expediente persistido.')
            case_elapsed = (perf_counter() - case_started) * 1000
            upload_ms.append(upload_elapsed)
            validation_ms.append(validation_elapsed)
            cases_ms.append(case_elapsed)
            rows.append({'registro': reference, 'id': dossier['id'], 'codigo_tupa': code,
                         'escenario': scenario, 'estado_procesamiento': dossier['estado'],
                         'resultado_esperado': expected, 'resultado_obtenido': flow['validation']['estado'],
                         'paginas': sum(len(d['paginas']) for d in dossier['documentos']),
                         'segmentos': len(dossier['documentos']), 'sha256': dossier['sha256'],
                         'pdf_original': 'originales/' + dossier['id'] + '.pdf',
                         'estado_enrutamiento': flow['routing'].get('estado', 'NO_HABILITADO'),
                         'confianza_modelo_sintetico': flow['routing'].get('confianza'),
                         'carga_ms': round(upload_elapsed, 3), 'validacion_ms': round(validation_elapsed, 3),
                         'caso_ms': round(case_elapsed, 3), 'origen': 'FICTICIO_GENERADO'})
            if progress and ((index + 1) % 50 == 0 or index + 1 == count):
                print(f'{index + 1}/{count} expedientes procesados y persistidos', flush=True)
    elapsed = perf_counter() - started
    with sqlite3.connect(database) as connection:
        expedientes = connection.execute('SELECT id, payload FROM expedientes ORDER BY id').fetchall()
        flujos = connection.execute('SELECT dossier_id, revision, payload FROM flujos_municipales ORDER BY dossier_id').fetchall()
    if len(expedientes) != count or len(flujos) != count:
        raise RuntimeError('El conteo físico de tablas no coincide con el lote.')
    if len({r['id'] for r in rows}) != count or len({r['sha256'] for r in rows}) != count:
        raise RuntimeError('Se detectaron identificadores o archivos repetidos.')
    for dossier_id, payload in expedientes:
        saved = json.loads(payload)
        if sha256((storage / (dossier_id + '.pdf')).read_bytes()).hexdigest() != saved['sha256']:
            raise RuntimeError('El original no coincide con el registro persistido.')
    write_csv(output / 'registros.csv', list(rows[0]), rows)
    # Estructura exacta de las tablas existentes; estos CSV no escriben en Supabase.
    write_csv(output / 'expedientes_supabase.csv', ['id', 'payload'],
              [{'id': key, 'payload': payload} for key, payload in expedientes])
    write_csv(output / 'flujos_municipales_supabase.csv', ['dossier_id', 'revision', 'payload'],
              [{'dossier_id': key, 'revision': revision, 'payload': payload} for key, revision, payload in flujos])
    summary = {'naturaleza': 'EVALUACION_ACADEMICA_CON_DATOS_FICTICIOS',
               'expedientes_persistidos': len(expedientes), 'flujos_persistidos': len(flujos),
               'pdf_distintos_por_sha256': len({r['sha256'] for r in rows}),
               'paginas_procesadas': sum(r['paginas'] for r in rows),
               'escenarios': dict(Counter(r['escenario'] for r in rows)),
               'procedimientos': dict(Counter(r['codigo_tupa'] for r in rows)),
               'resultados': dict(Counter(r['resultado_obtenido'] for r in rows)),
               'enrutamiento': dict(Counter(r['estado_enrutamiento'] for r in rows)),
               'duracion_segundos': round(elapsed, 3), 'concurrencia': 1,
               'latencia_carga': timings(upload_ms), 'latencia_validacion': timings(validation_ms),
               'latencia_caso_completo': timings(cases_ms),
               'entorno': {'sistema': platform.system(), 'python': platform.python_version(),
                           'base': 'SQLite local de pruebas', 'transporte': 'FastAPI TestClient ASGI'},
               'lectura': 'PDF_DIGITAL_TEXTO_EMBEBIDO', 'inferencias_ocr_sobre_imagen': 0,
               'llamadas_a_gemini_openai': 0, 'publicado_en_supabase': False,
               'advertencias': ['No es una medición de exactitud OCR ni generalización de IA.',
                   'Las validaciones usan evidencias y firmas explícitamente ficticias.',
                   'El enrutador usa un corpus sintético didáctico, sin calibración municipal.',
                   'La latencia ASGI local no equivale a latencia de Internet, Render o Supabase.',
                   'Importar solo CSV no transfiere los PDF originales al almacenamiento del backend.']}
    (output / 'resumen.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'consultas_verificacion_supabase.sql').write_text(
        "-- Solo lectura. Cuenta expedientes ficticios de este lote por su nombre de archivo.\n"
        "SELECT count(*) AS expedientes_del_lote FROM expedientes\n"
        "WHERE payload->>'filename' LIKE 'LOTE-%-FICTICIO.pdf';\n\n"
        "SELECT payload->>'status' AS estado, count(*) FROM expedientes\n"
        "WHERE payload->>'filename' LIKE 'LOTE-%-FICTICIO.pdf' GROUP BY payload->>'status';\n\n"
        "SELECT count(*) AS flujos_del_lote FROM flujos_municipales f\n"
        "JOIN expedientes e ON e.id = f.dossier_id\n"
        "WHERE e.payload->>'filename' LIKE 'LOTE-%-FICTICIO.pdf';\n", encoding='utf-8')
    (output / 'LEEME.txt').write_text(
        f'LOTE ACADEMICO: {count} expedientes ficticios distintos, sin datos de ciudadanos.\n'
        'registros.csv: índice de casos, resultados, IDs consultables y tiempos medidos.\n'
        'evaluacion.sqlite: base local, con tablas expedientes y flujos_municipales.\n'
        'originales/: PDFs con marca ficticia, uno por expediente.\n'
        'resumen.json: conteos verificados y condiciones de la ejecución.\n'
        'Los CSV *_supabase.csv tienen las columnas de las tablas existentes y permiten una importación manual revisada.\n'
        'No se ha escrito en Supabase. Importar datos solo en un entorno elegido expresamente.\n'
        'Para previsualizar PDF tras importar, también hay que transferir originales/ al STORAGE_DIR del backend.\n'
        'No subir credenciales ni desactivar permisos para realizar la importación.\n'
        'El lote usa PDF digitales y reglas académicas: no sustituye un benchmark OCR con imágenes ni expedientes reales.\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=500)
    parser.add_argument('--output', default='data/evaluacion-500')
    args = parser.parse_args()
    result = run_batch(args.output, args.count)
    print(json.dumps({'expedientes_persistidos': result['expedientes_persistidos'],
                      'flujos_persistidos': result['flujos_persistidos'],
                      'salida': str(Path(args.output).resolve())}, ensure_ascii=False))
