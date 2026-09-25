from src.domain.ports import DossierRepository
from src.domain.ports.workflow import (AdministrativeGateway, LocalRoutingModel, PrivacyFilter,
                                       ProcedureCatalog, WorkflowRepository)
from src.domain.workflow import (Conflict, DependencyUnavailable, NotFound, Workflow,
                                 WorkflowError, decide_route, evaluate_requirements)


class MunicipalWorkflow:
    def __init__(self, dossiers: DossierRepository, workflows: WorkflowRepository,
                 catalog: ProcedureCatalog, routing: LocalRoutingModel,
                 gateway: AdministrativeGateway, privacy: PrivacyFilter):
        self.dossiers, self.workflows, self.catalog = dossiers, workflows, catalog
        self.routing, self.gateway, self.privacy = routing, gateway, privacy

    def _dossier(self, dossier_id):
        dossier = self.dossiers.get(dossier_id)
        if dossier is None:
            raise NotFound("Expediente no encontrado.")
        return dossier

    def get(self, dossier_id):
        self._dossier(dossier_id)
        return self.workflows.get(dossier_id) or Workflow(dossier_id)

    def _edit(self, dossier_id, revision):
        dossier = self._dossier(dossier_id)
        if dossier.status != "PROCESADO":
            raise Conflict("Solo se admiten expedientes procesados correctamente.")
        flow = self.get(dossier_id)
        if flow.revision != revision:
            raise Conflict("La versión cambió. Consulte el flujo antes de reintentar.")
        return dossier, flow

    def validate(self, dossier_id, code, checks, revision, actor):
        dossier, flow = self._edit(dossier_id, revision)
        procedure = self.catalog.get(code)
        if procedure is None:
            raise NotFound("Código TUPA no incorporado al catálogo piloto.")
        validation = evaluate_requirements(procedure, dossier.documents, checks)
        flow.procedure_code, flow.validation = code, validation
        flow.routing = {}  # Una nueva validación invalida cualquier derivación anterior.
        for draft in flow.drafts:
            draft["vigente"] = False
        missing = [r["descripcion"] for r in validation["requisitos"] if r["estado"] == "FALTA"]
        if missing:
            self._draft(flow, "BORRADOR DE OBSERVACIONES - SIN VALIDEZ ADMINISTRATIVA\n"
                        + "Trámite: " + code + "\nVerificar/subsanar:\n- " + "\n- ".join(missing),
                        actor, "PLANTILLA_LOCAL", "OBSERVACION")
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
        self._draft(flow, content, actor, "EDICION_HUMANA", "PROYECTO")
        flow.record(actor, "VERSION_BORRADOR", {"version": len(flow.drafts)})
        self.workflows.save(flow, revision)
        return flow

    def approve_and_sign(self, dossier_id, revision, actor):
        _, flow = self._edit(dossier_id, revision)
        if not flow.drafts or not flow.drafts[-1]["vigente"]:
            raise Conflict("No existe borrador vigente para revisar.")
        # No marcar aprobado/firmado antes de una integración real, autenticada y verificable.
        self.gateway.require_available()
        raise DependencyUnavailable("Emisión administrativa todavía no implementada; no se firmó ni notificó.")

    def route(self, dossier_id, revision, actor):
        dossier, flow = self._edit(dossier_id, revision)
        if flow.validation.get("estado") != "CONFORME":
            raise Conflict("El expediente debe estar conforme documentalmente antes de derivarse.")
        procedure = self.catalog.get(flow.procedure_code)
        try:
            prediction = self.routing.predict(dossier)
            flow.routing = decide_route(prediction, {p.department for p in self.catalog.list()})
        except DependencyUnavailable:
            flow.routing = {"estado": "CLASIFICACION_MANUAL", "destino": None,
                            "sugerencia": procedure.department, "confianza": None,
                            "modelo": None, "alerta": True, "motivo": "MODELO_NO_CONFIGURADO",
                            "origen_sugerencia": "UNIDAD_RESPONSABLE_PUBLICADA_EN_TUPA",
                            "alcance": "BANDEJA_LOCAL_NO_SISGEDOC"}
        flow.record(actor, "ENRUTAMIENTO", flow.routing.copy())
        self.workflows.save(flow, revision)
        return flow

    def assign(self, dossier_id, department, revision, actor):
        _, flow = self._edit(dossier_id, revision)
        if flow.validation.get("estado") != "CONFORME":
            raise Conflict("Primero complete la validación documental.")
        if department not in {p.department for p in self.catalog.list()}:
            raise WorkflowError("Unidad no incluida en el catálogo piloto.")
        flow.routing = {"estado": "DERIVADO_LOCAL", "destino": department,
                        "confianza": None, "origen": "ASIGNACION_HUMANA", "alerta": False,
                        "alcance": "BANDEJA_LOCAL_NO_SISGEDOC"}
        flow.record(actor, "ASIGNACION_MANUAL", flow.routing.copy())
        self.workflows.save(flow, revision)
        return flow

    def indicators(self, dossier_id):
        flow = self.get(dossier_id)
        procedure = self.catalog.get(flow.procedure_code) if flow.procedure_code else None
        missing = sum(r["estado"] == "FALTA" for r in flow.validation.get("requisitos", []))
        return {"eta": {"estado": "NO_DISPONIBLE", "dias_habiles_predichos": None,
                         "motivo": "Sin histórico, modelo validado ni backlog municipal.",
                         "plazo_tupa_referencial_dias_habiles": procedure.published_days if procedure else None,
                         "fuente": procedure.source_url if procedure else None,
                         "advertencia": "El plazo publicado no es una predicción ni una fecha prometida."},
                "riesgo": {"estado": "NO_DISPONIBLE", "probabilidad_rechazo": None,
                            "motivo": "Sin histórico etiquetado ni modelo validado.",
                            "requisitos_faltantes_confirmados": missing,
                            "requiere_revision": flow.validation.get("estado") != "CONFORME"}}

    def privacy_preview(self, dossier_id, known_names):
        dossier = self._dossier(dossier_id)
        return self.privacy.preview("\n\n".join(d.text for d in dossier.documents), known_names)
