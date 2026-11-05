import csv
import json
import sqlite3
import pytest
from scripts.batch_demo_records import run_batch, timings


def test_batch_creates_distinct_records_real_pdfs_and_portable_exports(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://forbidden.invalid/no_tocar')
    monkeypatch.setenv('GEMINI_API_KEY', 'NEVER_EXPORT_KEY')
    monkeypatch.setenv('GEMINI_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_ENABLED', 'true')
    output = tmp_path / 'lote'
    result = run_batch(output, count=10, progress=False)
    assert result['expedientes_persistidos'] == result['flujos_persistidos'] == 10
    assert result['pdf_distintos_por_sha256'] == 10
    assert result['resultados'] == {'CONFORME': 5, 'OBSERVADO': 3, 'PENDIENTE_REVISION': 2}
    assert result['publicado_en_supabase'] is False
    assert result['llamadas_a_gemini_openai'] == 0 and result['inferencias_ocr_sobre_imagen'] == 0
    assert len(list((output / 'originales').glob('*.pdf'))) == 10
    with (output / 'registros.csv').open(encoding='utf-8', newline='') as source:
        records = list(csv.DictReader(source))
    assert len({r['id'] for r in records}) == len({r['sha256'] for r in records}) == 10
    with (output / 'expedientes_supabase.csv').open(encoding='utf-8', newline='') as source:
        exported = list(csv.DictReader(source))
    assert len(exported) == 10
    assert set(exported[0]) == {'id', 'payload'}
    assert all(json.loads(r['payload'])['status'] == 'PROCESADO' for r in exported)
    assert 'NEVER_EXPORT_KEY' not in (output / 'expedientes_supabase.csv').read_text(encoding='utf-8')
    with sqlite3.connect(output / 'evaluacion.sqlite') as connection:
        assert connection.execute('SELECT count(*) FROM expedientes').fetchone()[0] == 10
        assert connection.execute('SELECT count(*) FROM flujos_municipales').fetchone()[0] == 10
    assert json.loads((output / 'resumen.json').read_text(encoding='utf-8')) == result


@pytest.mark.parametrize('count', [0, -1, 1001, True])
def test_batch_rejects_invalid_counts(tmp_path, count):
    with pytest.raises(ValueError):
        run_batch(tmp_path / 'lote', count=count)


def test_batch_never_overwrites_an_existing_directory(tmp_path):
    (tmp_path / 'conservar.txt').write_text('sin cambios', encoding='utf-8')
    with pytest.raises(ValueError, match='no se sobrescriben'):
        run_batch(tmp_path, count=1)
    assert (tmp_path / 'conservar.txt').read_text(encoding='utf-8') == 'sin cambios'


def test_latency_summary_states_nearest_rank_p95():
    result = timings([4.0, 1.0, 2.0, 3.0])
    assert result['mediana_ms'] == 2.5 and result['p95_ms_rango_mas_cercano'] == 4
