"""PDFs ficticios y corpus didáctico. Ejecutar: python -m scripts.academic_examples --output DIR."""
import argparse
import json
from pathlib import Path
import pymupdf
from src.infrastructure.adapters.output.workflow import JSONProcedureCatalog
from src.infrastructure.adapters.output.academic import SyntheticRoutingModel

ROOT = Path(__file__).resolve().parents[1]


def demo_pdf(code='PA12115285', missing=None, ambiguous=False, unsigned=False, dni_conflict=False):
    catalog = JSONProcedureCatalog(ROOT / 'config/tupa_huancayo.json')
    procedure = catalog.get(code)
    subject = 'Consulta general sobre gestiones diversas' if ambiguous else procedure.name
    texts = ['EXPEDIENTE FICTICIO - DEMOSTRACION UNIVERSITARIA\nFORMULARIO UNICO DE TRAMITE\n'
             'NOMBRES: Persona Ficticia de Prueba\nDNI: 00000000\nASUNTO: ' + subject
             + '\nSOLICITO: ' + subject + '\nEVIDENCIA DEMO: solicitud']
    for requirement in procedure.requirements:
        if requirement.id == 'solicitud' or requirement.id == missing:
            continue
        fee = {'PA12115285': '153.20', 'PA121121B0': '2929.40', 'PE1027344C1': '216.00'}[code]
        title = ('DOCUMENTO NACIONAL DE IDENTIDAD\nRENIEC\nDNI: 00000000' if requirement.id == 'identidad'
                 else 'PLANO DE UBICACION\nESCALA: 1:500\nLAMINA: DEMO' if 'plano' in requirement.id
                 else 'RECIBO DE PAGO\nIMPORTE: ' + fee + '\nDNI: ' + ('99999999' if dni_conflict else '00000000') if requirement.id == 'pago'
                 else 'ANEXO FICTICIO: ' + requirement.id)
        marker = ('NO APLICA DEMO: ' if requirement.conditional else 'EVIDENCIA DEMO: ') + requirement.id
        signature = '\nFIRMA DEMO: PROFESIONAL FICTICIO' if requirement.id == 'plano_firmado' and not unsigned else ''
        texts.append('EXPEDIENTE FICTICIO - SIN VALIDEZ LEGAL\n' + title + '\n' + marker + signature)
    with pymupdf.open() as pdf:
        for index, text in enumerate(texts):
            page = pdf.new_page()
            page.insert_text((45, 35), 'DEMO UNIVERSITARIA - DATOS FICTICIOS - SIN VALIDEZ LEGAL', fontsize=11, color=(0.7, 0, 0))
            result = page.insert_textbox(pymupdf.Rect(45, 70, 550, 745), text, fontsize=12, lineheight=1.5)
            if result < 0:
                raise ValueError('El ejemplo no cabe en la página; ajuste la maquetación.')
            page.insert_text((45, 795), f'Codigo TUPA: {code} | Pagina {index + 1} | Solo prueba academica', fontsize=9)
        return pdf.tobytes(deflate=True)


def low_dpi_pdf():
    with pymupdf.open(stream=demo_pdf(), filetype='pdf') as source, pymupdf.open() as output:
        page = output.new_page()
        page.insert_image(page.rect, stream=source[0].get_pixmap(dpi=72).tobytes('png'))
        return output.tobytes(deflate=True)


def write_examples(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    examples = {
        '01-conforme-parametros.pdf': demo_pdf(),
        '02-falta-pago.pdf': demo_pdf(missing='pago'),
        '03-asunto-ambiguo.pdf': demo_pdf(ambiguous=True),
        '04-baja-resolucion.pdf': low_dpi_pdf(),
        '05-plano-sin-firma-demo.pdf': demo_pdf(unsigned=True),
        '06-conforme-zonificacion.pdf': demo_pdf('PA121121B0'),
        '07-conforme-funcionamiento.pdf': demo_pdf('PE1027344C1'),
        '08-inconsistencia-dni.pdf': demo_pdf(dni_conflict=True),
    }
    for name, content in examples.items():
        (output / name).write_bytes(content)
    model = SyntheticRoutingModel(JSONProcedureCatalog(ROOT / 'config/tupa_huancayo.json'))
    (output / 'corpus-sintetico.json').write_text(json.dumps(model.training_rows, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'LEEME.txt').write_text(
        'DEMO UNIVERSITARIA - sin datos reales ni validez legal.\n'
        'Usar ACADEMIC_DEMO=true y acceso de revisor.\n'
        '01: validar PA12115285 sin verificaciones manuales, evaluar destino y emitir simulacion.\n'
        '02: validacion OBSERVADO y esquela por falta de pago ficticio.\n'
        '03: conforme documental y clasificacion manual por asunto ambiguo.\n'
        '04: rechazo por resolucion inferior a 150 DPI.\n'
        '05: observacion por falta de firma ficticia.\n'
        '06: PA121121B0, destino Sub Gerencia de Planes y Cooperacion Tecnica Internacional.\n'
        '07: PE1027344C1, destino Gerencia de Promocion Economica y Turismo.\n'
        '08: PA12115285, DNI del recibo diferente al FUT/DNI; revision cruzada requerida, sin determinar fraude.\n'
        'El modelo se entrena con corpus-sintetico.json y no esta validado para expedientes reales.\n', encoding='utf-8')
    return examples


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='data/demo-universitaria')
    args = parser.parse_args()
    write_examples(args.output)
    print('Ejemplos ficticios generados en ' + str(Path(args.output).resolve()))
