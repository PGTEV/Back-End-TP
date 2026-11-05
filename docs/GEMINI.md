# Gemini para los borradores del sistema municipal

También se incorpora [auditoría TUPA asistida con Gemini](PMV_CINCO_HISTORIAS.md), sobre categorías/páginas y requisitos públicos. Es una acción separada de la generación de borradores y no certifica el contenido de los originales.

Gemini se añade como adaptador del mismo puerto DraftGenerator. Se conservan OpenAI, el endpoint autenticado `POST /api/expedientes/{id}/borradores/ia`, versiones, revisión optimista, auditoría, validación TUPA y las simulaciones universitarias existentes. No se alteran tablas ni se requieren dependencias nuevas; ambos proveedores utilizan httpx.

## Crear la clave y configurar Render

1. Crear o seleccionar un proyecto y obtener una clave en [Google AI Studio](https://aistudio.google.com/apikey). No enviar la clave por chat ni subirla a GitHub.
2. Comprobar en AI Studio el nivel y la cuota del proyecto. Según la [tarifa oficial](https://ai.google.dev/gemini-api/docs/pricing), Gemini 3.8 Flash dispone de nivel gratuito sujeto a disponibilidad/límites; no se garantiza acceso gratuito ni cuota para una cuenta concreta. Algunos proyectos pueden requerir verificación. No es necesario activar facturación para realizar esta configuración; si el proyecto está en nivel pagado, se aplican sus condiciones.
3. En Render, servicio backend → Environment, configurar:

```dotenv
AI_PROVIDER=gemini
GEMINI_ENABLED=true
GEMINI_API_KEY=colocar_la_clave_privada_del_proyecto_Google
GEMINI_MODEL=gemini-3.8-flash
GEMINI_TIMEOUT_SECONDS=60
OPENAI_ENABLED=false
PROTECT_DOSSIER_ROUTES=true
```

El valor de GEMINI_API_KEY mostrado es solo un marcador. Mantener REVIEWER_TOKEN, REVIEWER_ID, DATABASE_URL, CORS_ORIGINS y almacenamiento persistente actuales. Para los PDFs universitarios mantener ACADEMIC_DEMO=true. Desplegar primero el backend actualizado y después el frontend; en Vercel solo se conserva VITE_API_URL, ninguna clave de IA.

AI_PROVIDER admite `gemini`, `openai` o `none`. El valor predeterminado sigue siendo `openai` para conservar despliegues existentes. La selección es explícita: un error o una clave Gemini ausente **no** activa OpenAI ni provoca llamadas a ambos proveedores. Para deshabilitar toda IA remota usar AI_PROVIDER=none. Para volver a OpenAI usar AI_PROVIDER=openai y sus variables documentadas en [OPENAI.md](OPENAI.md).

## Probar

Abrir `/api/capacidades`: ia_generativa debe anunciar configurada=true, proveedor=GEMINI y el modelo configurado. Esto solo comprueba configuración, no hace inferencia ni valida la clave/cuota.

En el portal, cargar `01-conforme-parametros.pdf`, seleccionar PA12115285, auditar/guardar revisión y pulsar **Generar borrador con Gemini**. Se espera una nueva versión, origen GEMINI, modelo e ID devueltos por Google, y acción BORRADOR_IA. Editar y guardar otra versión para demostrar intervención humana. Con `02-falta-pago.pdf` se genera OBSERVACION y se mantiene el resultado observado. El botón explica bloqueos por revisión sin guardar, cambios en el editor o expediente ya emitido.

Un 429 significa cuota o frecuencia alcanzada: consultar los límites en AI Studio antes de reintentar. Un 401/403 indica que hay que revisar clave/permisos; un 404 indica modelo no disponible. Tiempo de espera, respuesta incompleta/bloqueada o JSON inválido conservan el flujo anterior. No se reintenta automáticamente ni se etiqueta una plantilla local como resultado de Gemini. Una generación puede consumir cuota aunque termine en timeout o conflicto concurrente.

Corrección de compatibilidad: se omite candidateCount, que la guía de Google identifica como no compatible con Gemini 3/4. No se comprobó que fuera la causa de una ejecución concreta en Render. Los diagnósticos ahora distinguen HTTP_400 (parámetros), HTTP_400_PRECONDICION (acceso del proyecto), HTTP_5XX, MAX_TOKENS (truncado), SOLICITUD_BLOQUEADA, BORRADOR_NO_JSON, ESQUEMA_INVALIDO y METADATOS_INCOMPLETOS. Solo se muestran códigos/mensajes locales; no se copian cuerpos ni mensajes libres del proveedor. Fuente: [guía de resolución de problemas](https://aistudio.google.com/docs/troubleshooting#check-api).

La corrección se verificó con 140 pruebas backend aprobadas y compileall correcto, sin llamadas reales a Google. No modifica el frontend ni requiere variables nuevas. Tras fusionarla, esperar el despliegue de Render y volver a generar una sola vez. Si falla, el código local entre corchetes permite identificar el punto del fallo sin compartir credenciales.

## Privacidad y alcance

El caso de uso construye la misma lista cerrada de hechos para ambos proveedores: procedimiento/requisitos públicos del catálogo, estados documentales, indicador de contradicciones y modo académico. No envía PDF, OCR, texto parcialmente enmascarado, campos extraídos, DNI/RUC, nombres, asunto, notas humanas, identificador del expediente o del evaluador. La clave viaja en la cabecera x-goog-api-key hacia el host fijo de Google, sin aparecer en URL.

Se usa generateContent con un solo candidato, respuesta JSON con esquema y límite de salida. Se rechazan respuestas bloqueadas o truncadas; las partes de razonamiento no se muestran. No se incorporan herramientas, historial de chat ni archivos remotos. El origen y los metadatos se guardan en el flujo local protegido. La generación no cambia la validación ni el destino y requiere revisión humana. El nivel gratuito de Google puede usar el contenido para mejorar sus productos, según sus condiciones; la minimización sigue siendo obligatoria. Esto no certifica cumplimiento integral de privacidad ni validez administrativa.

## Verificación

127 pruebas backend y 46 frontend aprobadas, TypeScript/build Vite, compileall y pip check correctos. Se prueban contrato REST, cabecera secreta sin clave en URL, errores, cuotas, respuestas bloqueadas/truncadas, exclusión de razonamiento, modelo inválido, selección de proveedor sin fallback, privacidad, persistencia, permisos, revisiones y UI con Gemini/OpenAI. Todas las llamadas a proveedores se simulan con MockTransport: no se ha utilizado una clave real ni se ha verificado inferencia real o cuota de tu cuenta. La prueba real queda pendiente de configurar Render y generar un borrador.

Fuentes oficiales consultadas: [API generateContent](https://ai.google.dev/api/generate-content), [salidas estructuradas](https://ai.google.dev/gemini-api/docs/generate-content/structured-output), [claves](https://ai.google.dev/gemini-api/docs/api-key), [modelo Gemini 3.8 Flash](https://aistudio.google.com/docs/models/gemini-3.8-flash).
