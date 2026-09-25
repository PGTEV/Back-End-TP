# Backend académico - Municipalidad Provincial de Huancayo

## Alcance y límites de esta entrega

Las siete historias aportadas por el equipo son el alcance del proyecto, no siete funcionalidades declaradas terminadas. Esta iteración añade una base local verificable sin inventar datos municipales, firmas, notificaciones o modelos entrenados.

| HU | Disponible y probado | Pendiente para cumplir toda la historia |
| --- | --- | --- |
| 01 | Extracción PDF/OCR, clasificación FUT/DNI/PLANO, persistencia y rechazo de ilegibilidad | Mejorar extracción de campos y clasificación de anexos adicionales; no clasifica todos los tipos del TUPA |
| 02 | Catálogo piloto trazable; candidatos por página; checklist revisado por humano; observaciones por plantilla | Validación automática del contenido y firmas, requisitos condicionales y actualización normativa institucional |
| 03 | Borradores versionados y auditados, persistencia y bloqueo de ediciones obsoletas | Generación por IA, identidad institucional, firma verificable, SISGEDOC, notificación y reintentos idempotentes |
| 04 | Contrato para modelo local, regla estricta >0.85, bandeja local manual y asignación humana | Modelo semántico validado con datos de la municipalidad; integración de bandejas institucionales |
| 05 | Plazo publicado con fuente, claramente separado del ETA (null) | Histórico, complejidad, backlog actualizado y modelo ETA validado |
| 06 | Conteo de faltantes confirmados; probabilidad null | Histórico etiquetado, definición de rechazo/reproceso, entrenamiento y evaluación del modelo |
| 07 | Vista previa local de enmascaramiento, sin mapa reversible expuesto | Detección integral de PII, autorización de proveedor y puerta segura de salida. Todo envío externo está deshabilitado |

No hay valores fijos de 12 días o 92% presentados como predicciones. Una derivación local no significa que SISGEDOC recibió el expediente. Un nombre escrito en un documento no acredita una firma. El sistema no certifica cumplimiento legal ni emite actos administrativos.

## Fuente de Huancayo

El PDF entregado por el usuario es una impresión de 12 páginas del índice de publicaciones, no el TUPA completo. Sus enlaces permitieron descargar el TUPA 2025 de 605 páginas.

- Índice oficial: https://www.gob.pe/institucion/munihuancayo/informes-publicaciones/1050892-texto-unico-de-procedimientos-administrativos-tupa
- TUPA base, OM 790-MPH/CM: https://cdn.www.gob.pe/uploads/document/file/8019739/1050892-texto-unico-de-procedimientos-administrativos-tupa-2025.pdf
- SHA256 del PDF base: `74d4305c6a6997c088409cc1951579cde5c5485b948a206683d31d01a1f83d53`.
- Copias descargadas: `data/fuentes/`, excluidas de Git por la política existente. El catálogo sí está versionable en `config/tupa_huancayo.json`; incluye URL, hash, páginas y versión.

Piloto seleccionado por relación con los PDFs de prueba y el ejemplo de licencia en HU05; no limita permanentemente el proyecto a estos tres trámites:

| Código oficial | Procedimiento | Páginas PDF / impresas | Plazo publicado, no ETA |
| --- | --- | --- | --- |
| PA121121B0 | Modificación de zonificación o zonificación específica | 75-76 / 72-73 | 30 días hábiles |
| PA12115285 | Certificado de parámetros urbanísticos y edificatorios | 524 / 521 | 5 días hábiles |
| PE1027344C1 | Licencia de funcionamiento de riesgo bajo, ITSE posterior | 80-81 / 77-78 | 2 días hábiles |

Los requisitos del catálogo son resúmenes de trabajo, no sustituyen las páginas originales. No se exige automáticamente copia del DNI cuando la fuente dice exhibirlo, ni copia de recibo cuando solo corresponde acreditar el pago. No se han cargado tasas para evitar aplicar montos o beneficios temporales sin revisión de vigencia.

Anexos revisados visualmente el 2026-09-24:

- DA 012-2025: cambios sobre determinados procedimientos de tránsito y desarrollo urbano, no sobre los tres códigos piloto. https://cdn.www.gob.pe/uploads/document/file/8341889/1050892-da25n012-se-modifica-en-los-siguientes-detalles.pdf
- DA 013-2025: prórroga de incentivos de la OM 785 hasta el 31-12-2025; no se aplica como beneficio vigente en 2026. https://cdn.www.gob.pe/uploads/document/file/8421490/1050892-da25n013-modificacion-hasta-el-31-12-2025.pdf
- El archivo rotulado `om25n795_modificacion-tupa.pdf` contiene una ordenanza sobre el Plan Vial y la ruta JU-1034, no una tabla de nuevos requisitos TUPA. No se aplicaron cambios al catálogo por el nombre del archivo. https://cdn.www.gob.pe/uploads/document/file/8421537/1050892-om25n795_modificacion-tupa.pdf

La revisión de estos anexos no certifica la ausencia de otras modificaciones en 2026. Debe validarse la vigencia antes de cualquier uso municipal real.

## Arquitectura hexagonal

- `src/domain/workflow.py`: entidades y reglas de requisitos/enrutamiento; no conoce HTTP, SQL ni OCR.
- `src/domain/privacy.py`: reglas locales de enmascaramiento.
- `src/domain/ports/workflow.py`: contratos de catálogo, persistencia, modelo local, privacidad e integración administrativa.
- `src/application/workflow.py`: coordina los casos de uso mediante esos contratos.
- `src/infrastructure/adapters/input/municipal.py`: validación HTTP y autenticación local del evaluador; no decide conformidad.
- `src/infrastructure/adapters/output/workflow.py`: catálogo JSON y SQL; adaptadores explícitamente no disponibles para modelo y emisión.
- `src/infrastructure/main.py`: composición/inyección de dependencias.

La tabla adicional `flujos_municipales` conserva el checklist, las versiones de borradores, la bandeja local y la auditoría. No modifica los PDF ni los registros existentes de extracción. La escritura usa comparación atómica de revisión: dos actualizaciones de una versión no pueden sobrescribirse silenciosamente. No existe un historial inviolable criptográficamente; no debe presentarse como tal.

## Probar sin cambiar datos existentes

Desde la raíz del proyecto, con un intérprete que tenga `requirements.txt` instalado:

```powershell
python -m scripts.demo_huancayo
python -m pytest -q
```

La demo usa un PDF ficticio, token efímero y base temporal. No envía correos, no llama a SISGEDOC y no altera la base local del usuario. Los datos de demo no se usan como histórico de entrenamiento.

## Probar con Swagger

1. Si no existe `.env`, copiar `.env.example` sin sobrescribir una configuración propia existente.
2. Configurar `REVIEWER_ID` con el identificador del evaluador de pruebas y `REVIEWER_TOKEN` con una clave propia de mínimo 32 caracteres. Puede generarse con `python -c "import secrets; print(secrets.token_urlsafe(32))"`. No compartirla ni subirla a Git.
3. Arrancar desde esta carpeta: `python -m uvicorn src.infrastructure.main:create_app --factory --host 127.0.0.1 --port 8000`. Si ya hay un servidor anterior, reiniciarlo en esta carpeta o usar otro puerto.
4. Abrir `/docs`. Consultar `GET /api/capacidades` y `GET /api/tupa/procedimientos`.
5. Pulsar **Authorize** y pegar solamente el token configurado. Es autenticación local de un revisor, no SSO municipal.
6. Cargar el PDF usando `POST /api/expedientes`. Copiar `id`.
7. Consultar `GET /api/expedientes/{id}/flujo`; comienza en revisión 0.
8. Ejecutar `POST /api/expedientes/{id}/validacion` con:

```json
{"revision": 0, "codigo_tupa": "PA12115285", "verificaciones": {}}
```

Esto identifica candidatos y deja los requisitos pendientes. No convierte un PDF sin firmas verificadas en conforme.

9. Para una observación de prueba, repetir con la revisión devuelta por el servidor:

```json
{
  "revision": 1,
  "codigo_tupa": "PA12115285",
  "verificaciones": {
    "pago": {"estado": "FALTA", "nota": "En este caso ficticio no se acredita el pago.", "paginas": []}
  }
}
```

La respuesta contiene `validation`, `drafts` y `audit`. Cada validación sustituye el checklist completo; incluya todas las verificaciones que quiera conservar. Una nueva validación invalida la derivación y los borradores anteriores, conservando su historial.

10. Editar mediante `POST /api/expedientes/{id}/borradores`, con `revision` actual y `contenido`. `GET .../flujo` permite comparar versiones.
11. Solo después de verificar todos los requisitos, marcar cada uno `CUMPLE`, o `NO_APLICA` únicamente cuando es condicional, con fundamento. Los números de página deben existir. La revisión manual debe cubrir contenido, firma, habilitación, pago y condiciones que correspondan; la mera presencia de una palabra no basta.
12. `POST .../enrutamiento` crea una entrada local de clasificación manual porque no existe modelo. `POST .../asignacion` permite resolverla indicando una unidad del catálogo.
13. `GET .../indicadores` devuelve plazo publicado y predicciones no disponibles. `POST .../privacidad/vista-previa` con `{"nombres_conocidos": []}` muestra el enmascaramiento sin transmitir nada.
14. `POST .../aprobar-firmar` devuelve 503 si existe un borrador vigente: está bloqueado hasta implementar integración auténtica. No modifica la firma ni el estado del borrador.

Si se recibe 409, obtener otra vez el flujo: la versión enviada ya no es actual. Un 401 indica token incorrecto; un 503 `REVISOR_NO_CONFIGURADO` indica configuración pendiente.

## Seguridad de prototipo

Usar exclusivamente en localhost y con documentos ficticios. Los endpoints originales HU01 siguen sin control por usuario para preservar su contrato anterior; los nuevos flujos requieren token. Antes de producción hacen falta autenticación/roles completos, autorización por expediente, protección de originales y copias de seguridad, política de retención, cifrado, límites de peticiones y tratamiento de datos personales aprobado institucionalmente.

El filtro de privacidad identifica DNIs de ocho dígitos, ciertos RUC/teléfonos/correos, nombres conocidos y líneas etiquetadas. Puede omitir identidades en texto libre y produce falsos positivos en otros números; no es anonimización garantizada. No hay adaptador de LLM remoto, por lo que no existe salida externa de texto en esta versión.
