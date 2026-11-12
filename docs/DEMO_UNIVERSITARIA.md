# Demostración universitaria HU01–HU04 con el TUPA de Huancayo

## Demostración local por roles

Ejecute desde la raíz del backend, con Python 3.12 y las dependencias de `requirements.lock.txt` instaladas.

```powershell
python -m scripts.run_academic_demo
```

El lanzador escucha en `127.0.0.1:8000`, crea SQLite y almacenamiento en un directorio temporal, genera los PDF ficticios e imprime los tokens de esta ejecución. Los tokens solo son válidos durante la sesión local. Termine con Ctrl+C. El directorio se retira al salir. Use el frontend local en `http://localhost:5173` con `VITE_API_URL=http://127.0.0.1:8000/api`. Para otro origen local, pase `--frontend-origin` al lanzador. El servicio se construye con `_env_file=None` y el proveedor externo desactivado.

| Cuenta | Permisos |
|---|---|
| `admin-demo` | Consulta todos los expedientes académicos de la sesión y los asigna a un responsable. |
| `evaluador-demo` | Carga, consulta y revisa expedientes propios. Puede editar borradores, evaluar el destino y asignar. |
| `evaluador-control` | Mismos permisos que el evaluador sobre expedientes propios. Sirve para mostrar la denegación de un expediente ajeno. |
| `responsable-*` | Consulta y aprueba únicamente los expedientes que le fueron asignados de forma explícita. |
| `revisor-legado` | Conserva el flujo de compatibilidad para expedientes sin propietario académico. |

El backend autentica el token y devuelve el identificador y rol mediante `GET /api/academico/sesion`. El alias del formulario no se usa en la auditoría. Fuera del lanzador, las cuentas se configuran mediante `ACADEMIC_ACCOUNTS` y solo se habilitan con `ACADEMIC_DEMO=true` y `PROTECT_DOSSIER_ROUTES=true`. Los campos son `id`, `role`, `token` y, para un responsable, `department` con el nombre exacto del catálogo. Use secretos aleatorios de al menos 32 caracteres y un responsable por área.

Cada página debe mostrar la marca EXPEDIENTE FICTICIO. Esa marca es una comprobación del ejercicio y no certifica que un documento carezca de datos reales. Los indicadores se muestran con el flujo TUPA guardado. El enrutamiento recomienda un área y la asignación queda a cargo de una persona. El plazo y el riesgo son estimaciones didácticas con datos generados. La firma, el registro SISGEDOC y la notificación son simulaciones locales sin validez legal.

### Guion por roles

1. Inicie sesión como `evaluador-demo`. Cargue el PDF `02-falta-pago.pdf`, elija el procedimiento `PA12115285` y ejecute la auditoría automática. Muestre el resultado observado y guarde una versión de la observación con una nota ficticia.
2. Cargue `01-conforme-parametros.pdf` y valide el mismo procedimiento. Muestre las estimaciones académicas y ejecute el enrutamiento. Copie el ID para la consulta del administrador.
3. Cierre sesión e intente consultar ese ID como `evaluador-control`. Después, entre como `admin-demo`, consulte el mismo ID y guarde la asignación a Gerencia de Desarrollo Urbano.
4. Inicie sesión con el responsable de esa gerencia. Consulte el expediente y ejecute **Aprobar y Firmar (simulación)**. Muestre el número DEMO, la firma y la notificación ficticia. Abra la auditoría y descargue un segmento PDF.

Para volver al prototipo anterior, cierre el lanzador, vuelva a las ramas base y use el almacenamiento previo. Mantenga separados los datos temporales del laboratorio. Desactivar las cuentas en el backend nuevo conserva el aislamiento de los expedientes académicos. No hay migraciones que revertir.

El modo académico permite demostrar los recorridos funcionales con expedientes ficticios. **No emite actos administrativos, no firma documentos de forma legal, no se conecta a SISGEDOC y no envía mensajes reales.** Las respuestas, el historial y la interfaz identifican esas operaciones como simulaciones.

## Documento TUPA verificado

Se revisó el PDF aportado `1050892-texto-unico-de-procedimientos-administrativos-tupa-2025.pdf`: 605 páginas y SHA-256 `74d4305c6a6997c088409cc1951579cde5c5485b948a206683d31d01a1f83d53`. Coincide exactamente con la fuente del catálogo existente. La portada contiene la Ordenanza Municipal 790-MPH/CM. El original no fue modificado ni se copió al repositorio.

Se comprobaron visualmente la portada y las páginas PDF 75, 76, 80, 81 y 524. El catálogo piloto conserva estos tres procedimientos:

- PA12115285: certificado de parámetros urbanísticos y edificatorios, Gerencia de Desarrollo Urbano, cuatro requisitos, cinco días hábiles publicados. Página PDF 524, numeración impresa 521.
- PA121121B0: modificación de zonificación o zonificación específica, Sub Gerencia de Planes y Cooperación Técnica Internacional, cinco requisitos, treinta días hábiles publicados. Páginas PDF 75–76, numeración impresa 72–73.
- PE1027344C1: licencia de funcionamiento de riesgo bajo con ITSE posterior, Gerencia de Promoción Económica y Turismo. Páginas PDF 80–81, numeración impresa 77–78. El catálogo desglosa requisitos condicionales para su revisión, sin exigir automáticamente copias adicionales.

La referencia real es el TUPA de 2025; los expedientes de prueba son ficticios. No se certifica que ese documento incluya todas las modificaciones normativas posteriores. El catálogo sigue siendo un piloto de tres trámites, no una importación completa de las 605 páginas.

La verificación reproducible queda en `config/tupa_source_verification.json`. Puede repetirse con:

```powershell
python -m scripts.verify_tupa_source "RUTA_AL_PDF"
```

El TUPA es una referencia de configuración: no debe cargarse como expediente ciudadano, cuyo límite predeterminado es de 30 páginas.

## Activar en Render

Publicar primero los cambios del backend y después los del frontend de la rama `codex/pmv-hu01-hu04`. En Environment del servicio de Render añadir:

```dotenv
ACADEMIC_DEMO=true
```

Conservar PROTECT_DOSSIER_ROUTES=true, REVIEWER_ID, REVIEWER_TOKEN privado, DATABASE_URL de Supabase, CORS y el almacenamiento ya configurados. No hacen falta claves de IA ni servicios externos. Guardar y desplegar. Al ingresar al nuevo frontend aparecerán el aviso DEMO UNIVERSITARIA y el enlace para descargar los expedientes ficticios.

Con ACADEMIC_DEMO=false se conserva la revisión humana y se bloquea la emisión sin integraciones, como antes. Los flujos ya simulados conservan su marca demo y sus comprobantes; no se convierten en registros reales al desactivar el modo.

## Recorrido para la exposición

1. Ingresar con el token del evaluador y descargar el ZIP del portal. Todos los PDFs llevan marcas visibles de datos ficticios y ausencia de validez legal.
2. Cargar `01-conforme-parametros.pdf`, seleccionar PA12115285 y pulsar **Auditar automáticamente (demostración)**. Debe quedar CONFORME y crearse un proyecto por plantilla académica.
3. Pulsar **Evaluar enrutamiento (modelo sintético)**. Debe proponerse y derivarse localmente a Gerencia de Desarrollo Urbano con probabilidad didáctica superior a 0.85.
4. Editar el proyecto y guardar una nueva versión. Abrir el historial para mostrar que el texto anterior permanece y consultar la auditoría del cambio.
5. Pulsar **Aprobar y Firmar (simulación)**. Se guardan una firma SIMULADA con huella del borrador, un registro SISGEDOC SIMULADO y una notificación entregada al buzón DEMO dentro del flujo. Se ve SIN VALIDEZ LEGAL. La emisión queda bloqueada para edición y una repetición con la revisión actual devuelve el mismo comprobante sin duplicarlo. Evaluar el destino antes de emitir.
6. Cargar `02-falta-pago.pdf` y auditar PA12115285. Debe quedar OBSERVADO y aparecer la alerta y la esquela de observación automáticamente.
7. Cargar `03-asunto-ambiguo.pdf`, auditar PA12115285 y evaluar enrutamiento. Debe ir a CLASIFICACION_MANUAL con alerta; el evaluador puede guardar una gerencia de destino.
8. Cargar `04-baja-resolucion.pdf`. Debe detenerse con «Documento ilegible, por favor vuelva a cargar el archivo».
9. `05-plano-sin-firma-demo.pdf` genera una observación por ausencia de la firma ficticia. `06-conforme-zonificacion.pdf` y `07-conforme-funcionamiento.pdf` permiten repetir la auditoría y el destino con los otros códigos.
10. `08-inconsistencia-dni.pdf` contiene un DNI distinto en el recibo ficticio. El informe debe detectar la diferencia al cargar y bloquear el conforme automático, sin acusar fraude.

El PDF de funcionamiento usa marcadores de NO APLICA para condiciones ficticias. Estos marcadores son un contrato didáctico, no una forma de acreditar requisitos ante una municipalidad. El auditor rechaza documentos que no lleven EXPEDIENTE FICTICIO en todas sus páginas.

## Qué es real y qué se simula

OCR, extracción, clasificación, SQL, control de versiones, auditoría y asignación local ejecutan código real. La auditoría automática de práctica comprueba marcadores de evidencia ficticia y la marca de firma ficticia del ejemplo; no verifica autenticidad, pago bancario o habilitación profesional. Los proyectos se redactan por plantilla y no mediante un LLM.

El modelo es un Naive Bayes multinomial entrenado en memoria con doce textos sintéticos para las tres unidades del catálogo. Usa el asunto y la solicitud del FUT, no una lectura del destino ya elegido por el evaluador. Un asunto sin vocabulario reconocido devuelve probabilidades iguales, por debajo de 0.85, y requiere clasificación manual. La probabilidad no está calibrada y no se presenta como precisión ni rendimiento municipal. Los textos de entrenamiento se incluyen en `corpus-sintetico.json` del ZIP.

La firma es un registro simulado con SHA-256 del contenido; no es una firma criptográfica de una persona. SISGEDOC y notificaciones son objetos persistidos en el mismo flujo SQL, sin transmisión externa. La bandeja es el destino local del expediente consultado, no una instalación del SISGEDOC municipal.

Así se pueden demostrar las historias en una exposición universitaria bajo un alcance académico explícito. Esto no acredita los criterios de validez legal o integración real del enunciado original.

## Generar ejemplos y pruebas

```powershell
python -m scripts.academic_examples --output data/demo-universitaria
python -m pytest -q
```

El frontend incluye el ZIP estático en `public/ejemplos-demo.zip`, compuesto por ocho PDFs, el corpus y las instrucciones. No contiene el PDF completo del TUPA ni credenciales.

Las pruebas cubren: auditoría automática conforme, pago y firma ficticios faltantes, DPI bajo, alta y baja probabilidad, asignación manual, edición, emisión simulada persistida, idempotencia, rechazo de edición posterior y rechazo de expedientes sin marca ficticia. La suite anterior continúa ejecutándose con ACADEMIC_DEMO=false.

Verificación de esta entrega: **77 pruebas backend y 36 frontend aprobadas**, junto con TypeScript, build Vite y compilación Python. Los PDFs se renderizaron y revisaron visualmente. La interfaz se verificó mediante pruebas DOM, sin una revisión visual en navegador real. No se enviaron archivos ni credenciales a producción ni se habilitó ACADEMIC_DEMO en el servicio activo.
