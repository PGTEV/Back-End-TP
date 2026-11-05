# Evaluación y aceptación HU01–HU04

**Ampliación para el trabajo universitario:** se incorporó un [modo académico opcional](DEMO_UNIVERSITARIA.md) con el TUPA verificado, expedientes ficticios, auditoría automática de práctica, modelo entrenado con textos sintéticos y emisión explícitamente simulada. Permite demostrar los recorridos; el análisis de cumplimiento municipal real que sigue permanece vigente para el modo normal.

**Resultado: cumplimiento parcial del conjunto solicitado. No se puede acreditar que las cuatro historias estén completas.** Se implementaron las funciones locales verificables; firma, SISGEDOC, notificación y predicción real siguen pendientes. No se dispone de sus integraciones ni de un conjunto histórico anonimizado de expedientes etiquetados.

Esta revisión parte del backend `PGTEV/Back-End-TP`, main `aa49f24`, y del frontend `RobelUC/ExpedientesMuniFront`, main `c0a5bc6`. Las ampliaciones están en la rama `codex/pmv-hu01-hu04` de cada repositorio. No se han fusionado ni desplegado estas ampliaciones en producción.

## HU01 — Extracción y procesamiento

**Escenario 1: implementado para los formatos soportados y probado con PDFs sintéticos.** PyMuPDF extrae texto digital y RapidOCR procesa escaneos; las reglas clasifican FUT, DNI y planos y guardan el agregado en SQL y el original en almacenamiento de archivos. Las páginas ambiguas permanecen DESCONOCIDO. Se añadió extracción conservadora de asunto, solicitud, nombres, domicilio, teléfono y correo cuando el FUT los etiqueta expresamente, conservando acentos. No se completan valores ausentes.

Límite: las reglas no equivalen a un modelo NLP validado con todos los formatos municipales. La unidad clasificada es cada página; no hay agrupación semántica general de anexos que ocupan varias páginas. Las pruebas prueban los casos que contienen, no una tasa de precisión sobre expedientes reales.

**Escenario 2: implementado el rechazo de DPI bajo e ilegibilidad detectada por el OCR; la detección universal de borrosidad sigue pendiente de calibración.** Se corrigió la tolerancia que aceptaba resoluciones ligeramente inferiores a 150 DPI. Se prueban 72, 149 y 149.8 DPI, y un escaneo sintético muy borroso. El rechazo usa exactamente «Documento ilegible, por favor vuelva a cargar el archivo», detiene la extracción y persiste ILEGIBLE sin documentos parciales. El DPI es efectivo, calculado sobre las imágenes principales; no se atribuye DPI ficticio a un PDF vectorial.

No se afirma detectar toda imagen borrosa: un OCR puede devolver alta confianza aun con defectos. Falta un conjunto representativo de capturas y una definición de calidad aceptable para calibrar ese criterio.

## HU02 — Validación normativa y auditoría

**Escenario 1: parcial, revisión documental humana.** El catálogo piloto aporta requisitos por código TUPA. Solo las verificaciones del evaluador pueden producir CONFORME y habilitar enrutamiento. La mera presencia de un plano o de la palabra FIRMA no acredita firma, habilitación profesional, pago ni validez legal. Se prueba explícitamente que un PDF con esas menciones sigue PENDIENTE_REVISION sin verificaciones humanas.

Pendiente: auditoría automática de contenido y firmas, fuentes verificables de pago/habilitación y catálogo normativo completo y vigente. No corresponde marcar conforme legal por similitud de texto ni por encontrar anexos.

**Escenario 2: implementada la alerta y la esquela al confirmar un faltante; detección legal automática pendiente.** Un requisito FALTA produce OBSERVADO, una alerta estructurada y un borrador de observación por plantilla local. Ahora incluye el fundamento y las páginas revisadas, y React muestra alerta y borrador. Se conserva el historial. El origen se identifica como PLANTILLA_LOCAL, no como generación por IA.

El sistema no convierte ausencia de una copia de recibo en incumplimiento automático: en los requisitos piloto hay acreditaciones y exhibiciones que no equivalen a exigir copias adjuntas. Las verificaciones son decisiones humanas fundamentadas.

## HU03 — Resolución con intervención humana

**Escenario 1: pendiente.** El sistema no puede registrar una firma electrónica verificable, actualizar SISGEDOC ni notificar a un ciudadano. La API responde 503 sin alterar el expediente; React deshabilita «Aprobar y Firmar» cuando las capacidades del servidor indican que faltan esas integraciones. No se generan constancias, firmas o notificaciones ficticias. Tampoco existe un generador de proyectos aprobatorios por IA.

Para completarlo se necesitan el proveedor y mecanismo de firma, documentación y entorno de pruebas de SISGEDOC, contrato de estados y notificaciones, identidad individual del firmante y un circuito de autorización y trazabilidad. El token compartido de prototipo no representa por sí solo una firma individual.

**Escenario 2: implementado en el flujo local.** React incorpora un editor del borrador, guarda nuevas versiones por el endpoint existente, recupera la versión vigente y muestra todo el historial y la auditoría. Se conservan autor, fecha y acción. La API rechaza ediciones con revisión obsoleta mediante 409. Se mantiene OBSERVACION al editar una esquela; después de una nueva validación conforme, el nuevo texto puede guardarse como PROYECTO conservando la esquela anterior. Se protegieron los cambios del editor frente a una validación TUPA simultánea y se ofrece recarga explícita que descarta cambios locales.

Esto actualiza el último borrador local, no un documento administrativo firmado o registrado externamente.

## HU04 — Enrutamiento predictivo

**Escenario 1: pendiente de modelo real.** Existe un puerto para el modelo y una regla que deriva localmente cuando la confianza es estrictamente mayor que 0.85. Las pruebas verifican 0.86, 0.85 y 0.84 en la orquestación mediante un doble de prueba; no son resultados de un modelo entrenado. No se publican probabilidades inventadas ni se sustituye un modelo por el destino del catálogo.

Para completarlo se necesita un histórico anonimizado con texto del asunto/FUT y gerencia destino, una separación de entrenamiento/validación, métricas y calibración de probabilidades, tratamiento de casos atípicos y un adaptador de inferencia local validado. La derivación local tampoco equivale a integración con SISGEDOC.

**Escenario 2: implementado el flujo humano y la regla de baja confianza; el cálculo semántico real está pendiente.** La regla envía probabilidades menores o iguales a 0.85 a CLASIFICACION_MANUAL. Sin modelo configurado, el sistema también solicita revisión manual, con confianza null y motivo explícito. React ahora muestra la alerta, una sugerencia identificada como procedente del TUPA y permite guardar una gerencia del catálogo. La asignación se persiste y audita como ASIGNACION_HUMANA. No existe una bandeja global por gerencia; se consulta el destino local de cada expediente cargado o recuperado por ID.

## Pruebas ejecutadas

- Backend: **67 pruebas aprobadas**, incluidos OCR real, casos DPI, PDF borroso sintético, extracción etiquetada, faltantes, versiones, auditoría, revalidación, persistencia, concurrencia, seguridad, CORS, Supabase y diagnósticos.
- Frontend: **34 pruebas aprobadas**, incluidas interacción con el editor, conflictos, protección de cambios locales, alertas, clasificación manual y asignación.
- La prueba HTTP de frontend utiliza FastAPI real en localhost y prueba carga, validación, dos versiones de borrador, auditoría, destino manual, rechazo de firma no disponible y rechazo de revisión obsoleta.
- TypeScript, build Vite y compilación Python aprobados. npm audit no reporta vulnerabilidades conocidas. Dos avisos de deprecación de Starlette/AnyIO no causan fallos.
- No se validaron firma legal, SISGEDOC, notificaciones ni un modelo predictivo real. No se probaron datos municipales personales en producción. No se verificó visualmente la interfaz en un navegador real; las pruebas de interacción usan DOM de pruebas.

## Compatibilidad y publicación

Se mantienen arquitectura, estilos, Supabase, seguridad del revisor y diagnósticos. No se añadieron rutas HTTP: React usa capacidades, flujo, validación, borradores, enrutamiento, asignación y aprobar-firmar ya existentes. Se añadieron campos de respuesta `integraciones` y `alertas`. Los registros previos siguen siendo legibles y no hay migración de tablas.

Para publicar estas mejoras locales, revisar y fusionar primero el backend y después el frontend. No hacen falta nuevas credenciales ni variables para esta ampliación. Las integraciones se siguen anunciando como no disponibles. No activar funciones externas ni transmitir texto personal a proveedores mientras no existan sus contratos y controles de privacidad.
