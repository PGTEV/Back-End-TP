# Borradores con OpenAI / GPT

También se admite [Gemini](GEMINI.md). Para usar OpenAI establecer AI_PROVIDER=openai; para deshabilitar ambos proveedores, AI_PROVIDER=none. No hay conmutación automática entre proveedores.

Se implementa una llamada real a `POST https://api.openai.com/v1/responses` mediante httpx, ya instalado. El puerto `DraftGenerator` mantiene el dominio y los casos de uso independientes del proveedor. No se añaden claves a Git ni al cliente React.

## Configuración en Render

En el servicio del backend, abrir Environment y configurar:

```dotenv
OPENAI_ENABLED=true
OPENAI_API_KEY=colocar_aqui_la_clave_privada_del_proyecto_OpenAI
OPENAI_MODEL=gpt-5.4-mini
OPENAI_TIMEOUT_SECONDS=60
PROTECT_DOSSIER_ROUTES=true
```

El valor de API key mostrado arriba es solo un marcador; pegar la clave únicamente en Render. Mantener REVIEWER_TOKEN propio (mínimo 32 caracteres), REVIEWER_ID y la base/almacenamiento actuales. Mantener CORS_ORIGINS con el dominio exacto de Vercel. Para los ejemplos ficticios conservar ACADEMIC_DEMO=true; GPT funciona también con revisión humana en modo normal.

Guardar los cambios y desplegar primero el backend actualizado; después el frontend actualizado en Vercel. En Vercel solo se necesita `VITE_API_URL=https://back-end-tp.onrender.com`. Nunca crear VITE_OPENAI_API_KEY. El proyecto OpenAI debe permitir el modelo elegido y disponer de cuota. El modelo es configurable y debe admitir Responses con Structured Outputs. Se verificó en la documentación oficial el soporte de `gpt-5.4-mini`; la disponibilidad de la cuenta no se ha comprobado.

`GET /api/capacidades` publica `ia_generativa.configurada`, proveedor y modelo, sin credenciales. Configurada significa que están presentes la activación, clave, modelo y protección de rutas; no es un diagnóstico de acceso/saldo ni realiza una llamada facturable.

## Uso y demostración

1. Iniciar sesión, cargar un PDF y guardar la revisión TUPA (o auditar el ejemplo ficticio).
2. Pulsar **Generar borrador con GPT**. La nueva ruta implementada es `POST /api/expedientes/{id}/borradores/ia`, con Bearer y cuerpo `{"revision": N}`. La solicitud cliente no incluye contenido del expediente.
3. Revisar el texto del editor y su procedencia: OPENAI, modelo devuelto por la API, ID de respuesta y versión del prompt. Se guardan nueva versión y acción BORRADOR_IA en la base. La respuesta HTTP es 201 con el flujo actualizado.
4. Corregir el borrador y guardar otra versión. Capturar el historial y la auditoría para el informe. Con el ejemplo sin recibo, el tipo es OBSERVACION; con expediente conforme es PROYECTO. Con pendientes o contradicciones se solicita revisión, sin convertirlo a conforme.

La generación no cambia el resultado de la validación ni el destino. La firma, SISGEDOC y notificación siguen con su alcance previamente documentado; disponer de GPT no convierte sus simulaciones en integraciones reales. La extracción OCR, segmentación, reglas TUPA y enrutamiento existentes se conservan. Esta incorporación es redacción generativa, no una nueva extracción o clasificación semántica de documentos.

## Datos que salen y límites

Se construye en el servidor una lista cerrada con nombre/código/gerencia/fuente públicos del TUPA, descripciones públicas de requisitos y estados de revisión, indicador de contradicciones y modo académico. **No se envían** PDF, texto OCR (ni su versión parcialmente enmascarada), campos extraídos, DNI/RUC, asunto, nombres, direcciones, nombre de archivo, ID del expediente, notas libres del evaluador ni identidad del revisor. El ID de respuesta de OpenAI queda asociado localmente al flujo.

Se usa JSON Schema estricto, sin herramientas ni conversaciones previas y con `store=false`. Esto no implica ausencia de toda retención del proveedor ni certifica cumplimiento legal integral. El filtro local de datos sigue siendo parcial y no autoriza enviar texto libre. El modelo puede equivocarse: todo resultado se presenta como borrador para revisión humana, sin afirmar firma ni resolución definitiva.

Sin configuración, el botón se deshabilita; una solicitud directa recibe 503 cuando ya hay validación. Fallos de autenticación, cuota, HTTP, timeout, rechazo o contenido inválido no se sustituyen por plantillas atribuidas a IA y no guardan una versión nueva. El flujo y borrador previos se conservan. Revisiones desactualizadas producen 409; no se reintenta automáticamente para evitar cargos repetidos. Se permite una generación simultánea por proceso; cada nueva generación explícita puede generar consumo. No existe límite diario de gasto dentro de la app: configurarlo en el proyecto del proveedor. Un timeout o conflicto concurrente puede haber consumido tokens aunque no se guarde el resultado.

## Verificación

Verificación de esta entrega: 102 pruebas backend y 45 frontend aprobadas, TypeScript y build Vite correctos, compileall y pip check correctos. Se incluyen pruebas del contrato HTTP de Responses, esquema, metadatos, minimización del payload, permisos, revisión, persistencia, errores, conservación de versiones y el botón GPT. Usan transporte simulado, ninguna clave ni llamada real a OpenAI. La prueba de inferencia real queda pendiente hasta configurar el proyecto en Render y generar un borrador. No se afirma calidad lingüística o normativa validada con expedientes reales.

Fuentes: [Structured Outputs — OpenAI Docs](https://developers.openai.com/api/docs/guides/structured-outputs), [GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
