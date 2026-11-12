from src.domain.ports import DossierRepository
from src.domain.intake import protect_and_compare
from src.domain.evidence_audit import evidence_facts, validate_ai_audit
from src.domain.ports.workflow import (AcademicIndicatorEstimator, AdministrativeGateway, LocalRoutingModel, PrivacyFilter,
                                       ProcedureCatalog, RequirementAuditor, WorkflowRepository, DraftGenerator, EvidenceAuditAssistant)
from src.domain.workflow import (Conflict, DependencyUnavailable, NotFound, Workflow,
                                 WorkflowError, decide_route, evaluate_requirements)


class MunicipalWorkflow:
    def __init__(self, dossiers: DossierRepository, workflows: WorkflowRepository,
                 catalog: ProcedureCatalog, routing: LocalRoutingModel,
                 gateway: AdministrativeGateway, privacy: PrivacyFilter, auditor: RequirementAuditor | None = None,
                 draft_generator: DraftGenerator | None = None,
                 evidence_assistant: EvidenceAuditAssistant | None = None,
                 academic_indicators: AcademicIndicatorEstimator | None = None,
                 routing_assessment: dict | None = None):
        self.dossiers, self.workflows, self.catalog = dossiers, workflows, catalog
        self.routing, self.gateway, self.privacy = routing, gateway, privacy
        self.auditor = auditor
        self.draft_generator = draft_generator
        self.evidence_assistant = evidence_assistant
        self.academic_indicators = academic_indicators
        self.routing_assessment = routing_assessment

    def _dossier(self, dossier_id):
        dossier = self.dossiers.get(dossier_id)
        if dossier is None:
            raise NotFound("Expediente no encontrado.")
        return dossier

    def get(self, dossier_id):
        self._dossier(dossier_id)
        return self.workflows.get(dossier_id) or Workflow(dossier_id)

    def _edit(self, dossier_id, revision, allow_emitted=False):
        dossier = self._dossier(dossier_id)
        if dossier.status != "PROCESADO":
            raise Conflict("Solo se admiten expedientes procesados correctamente.")
        flow = self.get(dossier_id)
        if flow.revision != revision:
            raise Conflict("La versión cambió. Consulte el flujo antes de reintentar.")
        if not allow_emitted and any(d.get('estado') == 'EMITIDO_DEMO' for d in flow.drafts):
            raise Conflict('La demostración ya fue emitida. Cree otro expediente para una nueva ejecución.')
        return dossier, flow

    def validate(self, dossier_id, code, checks, revision, actor):
        dossier, flow = self._edit(dossier_id, revision)
        procedure = self.catalog.get(code)
        if procedure is None:
            raise NotFound("Código TUPA no incorporado al catálogo piloto.")
        if self.auditor is not None:
            checks = {**self.auditor.checks(procedure, dossier), **checks}
            flow.demo = True
        validation = evaluate_requirements(procedure, dossier.documents, checks)
        _, consistency = protect_and_compare(dossier.documents)
        facts = evidence_facts(procedure, dossier.documents, consistency)
        validation['preauditoria_local'] = {'requisitos': facts['requisitos'],
                                           'sin_lectura_semantica_del_contenido': True,
                                           'requiere_revision_humana': True}
        cross_alerts = consistency['alertas']
        if cross_alerts:
            validation['estado'] = 'OBSERVADO' if validation['estado'] == 'OBSERVADO' else 'PENDIENTE_REVISION'
            validation['habilitado_enrutamiento'] = False
            validation['inconsistencias_cruzadas'] = cross_alerts
            validation['alertas'].extend({'codigo': alert['codigo'], 'requisito': 'cruce_' + str(index),
                                         'mensaje': alert['mensaje'], 'nota': 'Revisión humana requerida; no se determina fraude.'}
                                        for index, alert in enumerate(cross_alerts))
        if flow.demo:
            validation.update(simulado=True, advertencia='DEMO UNIVERSITARIA: evidencias y firmas ficticias. Sin validez administrativa.')
        flow.procedure_code, flow.validation = code, validation
        flow.routing = {}  # Una nueva validación invalida cualquier derivación anterior.
        for draft in flow.drafts:
            draft["vigente"] = False
        missing = [r["descripcion"] + "\n  Fundamento: " + r["nota"]
                   + "\n  Páginas revisadas: " + (", ".join(map(str, r["paginas_revisadas"])) or "Sin referencia de página")
                   for r in validation["requisitos"] if r["estado"] == "FALTA"]
        missing.extend('Revisar consistencia entre anexos: ' + alert['mensaje'] for alert in cross_alerts)
        if missing:
            self._draft(flow, "BORRADOR DE OBSERVACIONES - SIN VALIDEZ ADMINISTRATIVA\n"
                        + "Trámite: " + code + "\nVerificar/subsanar:\n- " + "\n- ".join(missing),
                        actor, "PLANTILLA_ACADEMICA" if flow.demo else "PLANTILLA_LOCAL", "OBSERVACION")
        elif flow.demo and validation['estado'] == 'CONFORME':
            self._draft(flow, 'PROYECTO APROBATORIO DE DEMOSTRACION - SIN VALIDEZ LEGAL\n'
                        + 'Expediente ficticio: ' + dossier.id + '\nProcedimiento: ' + procedure.name
                        + '\nCodigo TUPA: ' + code + '\nSe propone aprobar exclusivamente esta simulacion academica.\n'
                        + 'Sustento: evidencias ficticias completas verificadas por reglas de demostracion.\n'
                        + 'No constituye resolucion municipal ni acredita firma, pago o habilitacion real.',
                        actor, 'PLANTILLA_ACADEMICA', 'PROYECTO')
        flow.record(actor, "VALIDACION_TUPA", {"codigo": code, "resultado": validation})
        self.workflows.save(flow, revision)
        return flow

    def _draft(self, flow, content, actor, origin, kind):
        if not content.strip():
            raise WorkflowError("El borrador no puede estar vacío.")
        for draft in flow.drafts:
            draft["vigente"] = False
        flow.drafts.append({"version": len(flow.drafts) + 1, "contenido": content,
                            "autor": actor, "origen": origin, "tipo": kind, "vigente": True,
                            "estado": "BORRADOR", "firma": None, "sisgedoc": None,
                            "notificacion": None})

    def edit_draft(self, dossier_id, content, revision, actor):
        _, flow = self._edit(dossier_id, revision)
        if not flow.validation:
            raise Conflict("Primero seleccione y valide un procedimiento TUPA.")
        previous_version = len(flow.drafts)
        kind = (flow.drafts[-1]["tipo"] if flow.drafts and flow.drafts[-1]["vigente"]
                else "OBSERVACION" if flow.validation.get("estado") == "OBSERVADO" else "PROYECTO")
        self._draft(flow, content, actor, "EDICION_HUMANA", kind)
        flow.record(actor, "VERSION_BORRADOR", {"version": len(flow.drafts),
                    "version_anterior": previous_version, "tipo": kind})
        self.workflows.save(flow, revision)
        return flow

    def audit_with_ai(self, dossier_id, revision, actor):
        dossier, flow = self._edit(dossier_id, revision)
        if not flow.validation or not flow.procedure_code:
            raise Conflict('Primero seleccione y guarde la revisión TUPA.')
        if self.evidence_assistant is None:
            raise DependencyUnavailable('La auditoría con Gemini no está configurada. Revise las variables del proveedor en Render.')
        procedure = self.catalog.get(flow.procedure_code)
        if procedure is None:
            raise NotFound('Procedimiento no disponible en el catálogo.')
        _, consistency = protect_and_compare(dossier.documents)
        facts = evidence_facts(procedure, dossier.documents, consistency)
        result = self.evidence_assistant.analyze(facts)
        findings = validate_ai_audit(result, facts)
        documents = {d['documento']: d for d in facts['documentos']}
        report = {key: result[key] for key in ('proveedor', 'modelo', 'respuesta_id', 'version_prompt')}
        report.update(hallazgos=[{**f, 'paginas': sorted({page for index in f['documentos']
                                                       for page in documents[index]['paginas']})} for f in findings],
                      cruce_local=facts['cruce_local'], requiere_revision_humana=True,
                      fuente=procedure.source_url, paginas_fuente=list(procedure.pdf_pages),
                      alcance='ASISTENCIA_SOBRE_METADATOS; NO_VERIFICA_CONTENIDO_FIRMAS_O_PAGOS',
                      transmision={'ocr': False, 'pdf': False, 'valores_personales': False},
                      fraude_determinado=False)
        # No aceptar una conclusión del LLM como prueba ni modificar verificaciones humanas.
        flow.validation['auditoria_ia'] = report
        flow.record(actor, 'AUDITORIA_IA', report)
        self.workflows.save(flow, revision)
        return flow

    def generate_draft(self, dossier_id, revision, actor):
        _, flow = self._edit(dossier_id, revision)
        if not flow.validation or not flow.procedure_code:
            raise Conflict("Primero guarde la validación TUPA.")
        if self.draft_generator is None:
            raise DependencyUnavailable("La IA generativa no está configurada. Revise el proveedor y sus variables en Render.")
        procedure = self.catalog.get(flow.procedure_code)
        if procedure is None:
            raise NotFound("Procedimiento no disponible en el catálogo.")
        state = flow.validation.get('estado')
        kind = 'PROYECTO' if state == 'CONFORME' else 'OBSERVACION'
        # Lista cerrada: nada de OCR, nombres, notas humanas, identificadores ni archivos.
        requirements = {r['id']: r for r in flow.validation.get('requisitos', [])}
        facts = {
            'tipo_borrador': kind, 'demostracion': flow.demo,
            'procedimiento': {'codigo': procedure.code, 'nombre': procedure.name,
                              'gerencia': procedure.department, 'fuente': procedure.source_url},
            'resultado_documental': state,
            'requiere_revision_cruzada': bool(flow.validation.get('inconsistencias_cruzadas')),
            'requisitos': [{'descripcion': r.description,
                           'estado': requirements.get(r.id, {}).get('estado', 'PENDIENTE')}
                          for r in procedure.requirements],
        }
        generated = self.draft_generator.generate(facts)
        self._draft(flow, 'BORRADOR PARA REVISIÓN HUMANA - SIN VALIDEZ ADMINISTRATIVA\n'
                    + generated['contenido'], actor, generated['proveedor'], kind)
        flow.drafts[-1]['ia'] = {key: generated[key] for key in
                                ('proveedor', 'modelo', 'respuesta_id', 'version_prompt')}
        flow.record(actor, 'BORRADOR_IA', {'version': len(flow.drafts), 'tipo': kind,
                                        **flow.drafts[-1]['ia']})
        self.workflows.save(flow, revision)
        return flow

    def approve_and_sign(self, dossier_id, revision, actor, responsible_id=None):
        _, flow = self._edit(dossier_id, revision, allow_emitted=True)
        if responsible_id is not None and flow.routing.get("responsable_id") != responsible_id:
            raise NotFound("Expediente no encontrado.")
        if not flow.drafts or not flow.drafts[-1]["vigente"]:
            raise Conflict("No existe borrador vigente para revisar.")
        # No marcar aprobado/firmado antes de una integración real, autenticada y verificable.
        self.gateway.require_available()
        if not flow.demo or flow.validation.get('estado') != 'CONFORME' or flow.drafts[-1]['tipo'] != 'PROYECTO':
            raise Conflict('Solo se puede emitir un proyecto conforme de demostración.')
        if flow.drafts[-1].get('estado') == 'EMITIDO_DEMO':
            return flow
        receipt = self.gateway.issue(dossier_id, flow.drafts[-1], actor)
        flow.drafts[-1].update(receipt)
        flow.record(actor, 'EMISION_SIMULADA', {'version': flow.drafts[-1]['version'],
                    'registro_demo': receipt['sisgedoc']['registro'], 'validez_legal': False})
        self.workflows.save(flow, revision)
        return flow

    def route(self, dossier_id, revision, actor):
        dossier, flow = self._edit(dossier_id, revision)
        if flow.validation.get("estado") != "CONFORME":
            raise Conflict("El expediente debe estar conforme documentalmente antes de derivarse.")
        if self.auditor is not None and not flow.demo:
            raise Conflict('Valide primero el expediente ficticio en modo académico.')
        procedure = self.catalog.get(flow.procedure_code)
        academic_roles = dossier.academic_owner is not None
        assessment = self.routing_assessment if academic_roles else None
        try:
            if assessment is not None and not assessment["aprobada"]:
                raise DependencyUnavailable("Evaluación sintética de enrutamiento insuficiente.")
            prediction = self.routing.predict(dossier)
            flow.routing = decide_route(prediction, {p.department for p in self.catalog.list()})
            if flow.demo:
                flow.routing.update(simulado=True, alcance='BANDEJA_ACADEMICA_LOCAL',
                                    datos_modelo='SINTETICOS', probabilidad_calibrada=False)
            if academic_roles and flow.routing["destino"] is not None:
                flow.routing.update(estado="SUGERENCIA_ACADEMICA", destino=None)
        except DependencyUnavailable:
            flow.routing = {"estado": "CLASIFICACION_MANUAL", "destino": None,
                            "sugerencia": procedure.department, "confianza": None,
                            "modelo": None, "alerta": True, "motivo": "MODELO_NO_CONFIGURADO",
                            "origen_sugerencia": "UNIDAD_RESPONSABLE_PUBLICADA_EN_TUPA",
                            "alcance": "BANDEJA_LOCAL_NO_SISGEDOC"}
        if assessment is not None:
            flow.routing["evaluacion_sintetica"] = assessment
            if not assessment["aprobada"]:
                flow.routing["motivo"] = "EVALUACION_SINTETICA_INSUFICIENTE"
        flow.record(actor, "ENRUTAMIENTO", flow.routing.copy())
        self.workflows.save(flow, revision)
        return flow

    def assign(self, dossier_id, department, revision, actor, responsible_id=None):
        _, flow = self._edit(dossier_id, revision)
        if flow.validation.get("estado") != "CONFORME":
            raise Conflict("Primero complete la validación documental.")
        if department not in {p.department for p in self.catalog.list()}:
            raise WorkflowError("Unidad no incluida en el catálogo piloto.")
        flow.routing = {"estado": "DERIVADO_LOCAL", "destino": department,
                        "confianza": None, "origen": "ASIGNACION_HUMANA", "alerta": False,
                        "alcance": "BANDEJA_LOCAL_NO_SISGEDOC"}
        if responsible_id is not None:
            flow.routing["responsable_id"] = responsible_id
        flow.record(actor, "ASIGNACION_MANUAL", flow.routing.copy())
        self.workflows.save(flow, revision)
        return flow

    def indicators(self, dossier_id):
        flow = self.get(dossier_id)
        procedure = self.catalog.get(flow.procedure_code) if flow.procedure_code else None
        requirements = flow.validation.get("requisitos", [])
        missing = sum(r["estado"] == "FALTA" for r in requirements)
        result = {"eta": {"estado": "NO_DISPONIBLE", "dias_habiles_predichos": None,
                         "motivo": "Sin histórico, modelo validado ni backlog municipal.",
                         "plazo_tupa_referencial_dias_habiles": procedure.published_days if procedure else None,
                         "fuente": procedure.source_url if procedure else None,
                         "advertencia": "El plazo publicado no es una predicción ni una fecha prometida."},
                "riesgo": {"estado": "NO_DISPONIBLE", "probabilidad_rechazo": None,
                            "motivo": "Sin histórico etiquetado ni modelo validado.",
                            "requisitos_faltantes_confirmados": missing,
                            "requiere_revision": flow.validation.get("estado") != "CONFORME"}}
        if self.academic_indicators and procedure and flow.demo:
            dossier = self._dossier(dossier_id)
            if dossier.academic_owner is not None:
                pages = len({page for document in dossier.documents for page in document.pages})
                pending = sum(requirement["estado"] == "PENDIENTE" for requirement in requirements)
                result["academico"] = self.academic_indicators.predict(
                    procedure.published_days, pages, missing, pending,
                    bool(flow.validation.get("inconsistencias_cruzadas")))
        return result

    def privacy_preview(self, dossier_id, known_names):
        dossier = self._dossier(dossier_id)
        return self.privacy.preview("\n\n".join(d.text for d in dossier.documents), known_names)
