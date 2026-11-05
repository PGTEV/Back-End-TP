# Extracción, segmentación, privacidad y auditoría TUPA

Esta entrega conecta las cinco historias con el flujo existente. La IA del sistema combina OCR local (RapidOCR/PP-OCR) y asistencia generativa Gemini. No depende de enviar los originales al proveedor. No afirma certificación de cumplimiento legal, detección de fraude ni validación autónoma de firmas.

## HU-01: extraer texto y datos de los anexos

El ingreso POST /api/expedientes extrae texto digital o utiliza OCR local para páginas escaneadas. Extrae campos explícitamente etiquetados y guarda documentos e informes en la base de datos. Conserva el rechazo de ilegibles/baja resolución y los estados de error. Esto se ejecuta al cargar, sin una llamada facturable a Gemini.

Demostración: cargar 01-conforme-parametros.pdf y comprobar los campos del formulario/DNI. Usar el ejemplo de baja resolución para comprobar el rechazo. Los datos originales quedan en el circuito autorizado del backend; no se envían al modelo generativo.

## HU-02: clasificar y separar páginas

El clasificador local soporta FUT, DNI, PLANO y RECIBO_PAGO. Cada página se convierte en un segmento descargable, con categoría, páginas fuente y método de extracción. Las categorías ambiguas permanecen DESCONOCIDO y requieren revisión. La separación es conservadora por página: no se afirma agrupación semántica perfecta de anexos de varias páginas.

Demostración: en el ejemplo conforme identificar los cuatro tipos y descargar el segmento del recibo para verificar que contiene solo su página. La ruta de descarga requiere Bearer cuando PROTECT_DOSSIER_ROUTES=true y nunca pone credenciales en la URL.

## HU-03: proteger datos antes del procesamiento externo

Al ingreso se produce una proyección local parcialmente enmascarada, con tokens consistentes de DNI/RUC, nombres y otros datos etiquetados. La interfaz protegida y la exportación existentes se conservan. Esa proyección NO es autorización para enviar texto libre a modelos remotos.

Para Gemini se construye otra proyección mediante una lista cerrada: categorías, números de página, presencia de identidad (booleano), requisitos públicos del TUPA y resultado booleano del cruce local. Se excluyen texto OCR incluso enmascarado, PDF, nombre de archivo, DNI/RUC, nombres, direcciones, contactos, identificador del expediente, notas y otros campos libres. El revisor no tiene que anonimizar manualmente antes de usar la auditoría. Las claves permanecen en Render.

La lectura local debe acceder al documento para extraer sus datos; la protección indicada se aplica antes de la transmisión al proveedor externo. El original permanece guardado para revisión autorizada. El enmascaramiento de texto es parcial y no garantiza anonimización irreversible; el control de egreso evita depender de esa garantía. Para operar con ciudadanos reales se requiere además la evaluación institucional de base jurídica, accesos, retención, información al titular y proveedores. No se declara cumplimiento integral de la [Ley 29733](https://www.gob.pe/institucion/anpd/normas-legales/2018427-29733-2011) por incorporar estas medidas.

## HU-04: cruzar evidencias con TUPA

Cada revisión TUPA guardada incorpora preauditoria_local con correspondencia de categorías a requisitos públicos. EVIDENCIA_CANDIDATA significa que hay un documento de una categoría útil; SIN_EVIDENCIA indica ausencia de una categoría reconocida; REVISION_HUMANA cubre condiciones, documentos desconocidos o requisitos sin correspondencia de categoría. Ninguno equivale automáticamente a CUMPLE.

El botón **Analizar requisitos con Gemini** utiliza la ruta nueva implementada POST /api/expedientes/{id}/auditoria/ia con Bearer y cuerpo {"revision": N}. Requiere una revisión TUPA guardada y devuelve 201 con el flujo actualizado. Gemini explica la relación entre requisitos y metadatos protegidos; NO inspecciona el contenido original. El servidor exige exactamente los requisitos del catálogo, los hallazgos locales y las referencias de documentos existentes. Rechaza requisitos inventados, páginas inexistentes, CUMPLE/CONFORME generados por IA o formatos inesperados.

El informe incluye modelo, ID de respuesta, versión de prompt, páginas candidatas y páginas fuente del TUPA, y se persiste con acción AUDITORIA_IA. Las ejecuciones anteriores quedan en la auditoría. La operación no sobrescribe verificaciones humanas, borradores, estado documental o destino. Una revisión TUPA posterior invalida el informe vigente; su registro previo permanece en el log.

Se conserva la auditoría automática de evidencias ficticias para la demostración universitaria y el botón de generación de borradores como acciones separadas. Los recibos pueden ayudar a revisar el pago sin convertirse automáticamente en un anexo obligatorio. La exhibición de DNI no se convierte en obligación de adjuntar una copia. El catálogo sigue limitado a tres procedimientos de Huancayo con referencias al TUPA 2025; no es validación de todo el TUPA ni certificación normativa actualizada.

## HU-05: comparar datos entre anexos

El cruce local compara DNI y RUC explícitos entre anexos y detecta varios DNI en una página. Las diferencias generan alertas con fuentes/páginas y valores protegidos, sin afirmar fraude ni ignorar posibles representantes/pagadores o errores OCR. Una contradicción impide el falso CONFORME y el enrutamiento aun si los requisitos se marcaron manualmente CUMPLE. Gemini solo recibe el resultado del cruce y campos comparados; no necesita los identificadores originales para explicarlo.

Demostración: cargar 08-inconsistencia-dni.pdf. Revisar el conflicto formulario/recibo y comprobar que se bloquea la derivación. Con una revisión TUPA guardada, ejecutar la auditoría Gemini para ver el indicador de diferencias junto al informe de requisitos. La alerta es de inconsistencia documental, no una acusación de fraude.

## Despliegue y pruebas

Fusionar primero backend y después frontend. No se requieren migraciones ni nuevas variables sobre la [configuración Gemini existente](GEMINI.md). GET /api/capacidades anuncia ia_generativa.auditoria_tupa=true únicamente cuando el adaptador Gemini está configurado. Configurada no comprueba cuota o acceso real. OpenAI continúa disponible para borradores; esta auditoría asistida se incorpora para Gemini.

La auditoría es explícita para evitar gastar cuota en cada carga, edición o recarga. Se deshabilita si hay cambios sin guardar, durante una solicitud o después de emitir el expediente. Errores de Google o resultados inválidos conservan la revisión anterior; conflictos de versión devuelven 409. Los diagnósticos conservan la corrección de compatibilidad que elimina candidateCount. No se desactivan filtros, no se reintenta automáticamente ni se cambia a otro proveedor.

Verificación: 154 pruebas backend y 49 frontend aprobadas; TypeScript, compilación Vite, compileall y pip check correctos. Las pruebas cubren el ingreso OCR, separación, privacidad, cruce, protección contra falso conforme, correspondencia TUPA, egreso mínimo, persistencia, autenticación, revisiones y rechazo de hallazgos inventados. Las llamadas a Gemini se simulan en pruebas: la inferencia y calidad de una respuesta real siguen pendientes de la clave/cuota del proyecto en Render. Referencia técnica: [salidas estructuradas Gemini](https://aistudio.google.com/docs/structured-output?generate-content=true).
