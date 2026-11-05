import pytest
from src.domain.classification import classify
from src.domain.valueObjects import Page


def document(text):
    return classify(Page(1, text, 1.0, "TEXTO_PDF"))


@pytest.mark.parametrize("scale", ["1/500", "1:500", "1 / 500", "1 : 500", "1/ 500"])
def test_scale_formats_are_normalized(scale):
    result = document(f"PLANO DE UBICACIÓN\nESCALA {scale}\nLÁMINA U01")
    assert result.type == "PLANO"
    assert result.fields["escala"] == "1:500"


@pytest.mark.parametrize("text", [
    "Considerando que se aprobó la propuesta del Plano de Desarrollo Metropolitano de Huancayo.",
    "MEMORIA DESCRIPTIVA\nSe adjunta un plano de ubicación a escala 1/500.",
    "PLANO DE DESARROLLO METROPOLITANO\nEl informe estudia su escala territorial.",
    "INFORME\nESCALA: 1/500\nLÁMINA: U01",
])
def test_mentions_and_isolated_labels_do_not_make_a_plan(text):
    assert document(text).type == "DESCONOCIDO"


def test_scale_keeps_source_text():
    original = "PLANO DE UBICACION\nESCALA 1/500"
    result = document(original)
    assert result.text == original
    assert result.fields["escala"] == "1:500"


def test_fut_extracts_only_explicit_labels_and_preserves_accents():
    result = document('FORMULARIO UNICO DE TRAMITE\nASUNTO: Parámetros urbanísticos\n'
                      'Nombres y apellidos: Persona Ficticia\nDOMICILIO LEGAL: Dirección de prueba\n'
                      'TELÉFONO: 999000111\nCORREO ELECTRÓNICO: prueba@example.invalid')
    assert result.type == 'FUT'
    assert result.fields['asunto'] == 'Parámetros urbanísticos'
    assert result.fields['nombres'] == 'Persona Ficticia'
    assert result.fields['domicilio'] == 'Dirección de prueba'
    assert result.fields['telefono'] == '999000111'
    assert result.fields['correo'] == 'prueba@example.invalid'
    assert 'apellidos' not in result.fields


def test_missing_fut_labels_are_not_invented():
    result = document('FORMULARIO UNICO DE TRAMITE\nSe menciona un asunto en texto libre sin etiqueta.')
    assert 'asunto' not in result.fields
    assert 'nombres' not in result.fields
