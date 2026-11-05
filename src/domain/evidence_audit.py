"""Proyección cerrada de evidencias: ningún texto o valor personal sale a la IA."""
from src.domain.workflow import DependencyUnavailable

DOCUMENT_TYPES = {'FUT', 'DNI', 'PLANO', 'RECIBO_PAGO', 'DESCONOCIDO'}


def evidence_facts(procedure, documents, consistency):
    evidence = [{'documento': index, 'tipo': d.type if d.type in DOCUMENT_TYPES else 'DESCONOCIDO',
                 'paginas': list(d.pages), 'identidad_declarada': bool(d.fields.get('dni') or d.fields.get('ruc'))}
                for index, d in enumerate(documents)]
    unknown = any(d['tipo'] == 'DESCONOCIDO' for d in evidence)
    requirements = []
    for requirement in procedure.requirements:
        # Un recibo puede ayudar a revisar el pago, sin convertirlo en anexo obligatorio.
        types = requirement.document_types or (('RECIBO_PAGO',) if requirement.id == 'pago' else ())
        candidates = [d['documento'] for d in evidence if d['tipo'] in types]
        status = ('EVIDENCIA_CANDIDATA' if candidates else 'REVISION_HUMANA'
                  if unknown or requirement.conditional or not requirement.document_types or requirement.id == 'identidad'
                  else 'SIN_EVIDENCIA')
        requirements.append({'id': requirement.id, 'descripcion': requirement.description,
                             'condicional': requirement.conditional,
                             'tipos_candidatos': list(types),
                             'documentos_candidatos': candidates, 'hallazgo_local': status})
    return {'procedimiento': {'codigo': procedure.code, 'nombre': procedure.name,
                              'fuente': procedure.source_url, 'paginas_fuente': list(procedure.pdf_pages)},
            'documentos': evidence, 'requisitos': requirements,
            'cruce_local': {'requiere_revision': bool(consistency['alertas']),
                            'campos_comparados': [k for k in ('dni', 'ruc') if k in consistency['campos_comparados']]},
            'politica': 'SOLO_TIPOS_PAGINAS_PRESENCIA_Y_RESULTADO_DE_CRUCE; SIN_PDF_OCR_NI_PII'}


def validate_ai_audit(result, facts):
    """No aceptar requisitos, estados, páginas o afirmaciones probatorias inventados."""
    invalid = DependencyUnavailable('La auditoría IA devolvió referencias o hallazgos no verificables. La revisión anterior se conserva.')
    findings = result.get('hallazgos')
    expected = {r['id']: r for r in facts['requisitos']}
    if not isinstance(findings, list) or len(findings) != len(expected):
        raise invalid
    seen = set()
    for item in findings:
        if not isinstance(item, dict) or set(item) != {'requisito', 'hallazgo', 'documentos', 'explicacion'}:
            raise invalid
        key = item['requisito']
        if not isinstance(key, str) or key not in expected or key in seen:
            raise invalid
        seen.add(key)
        if item['hallazgo'] != expected[key]['hallazgo_local']:
            raise invalid
        references = item['documentos']
        if (not isinstance(references, list) or any(type(i) is not int for i in references)
                or len(references) != len(set(references))
                or set(references) != set(expected[key]['documentos_candidatos'])):
            raise invalid
        explanation = item['explicacion']
        if not isinstance(explanation, str) or not 1 <= len(explanation.strip()) <= 2000:
            raise invalid
    return findings
