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
