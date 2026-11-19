# Paso 7 - Aplicación del plan OWASP

Fecha: 19 de noviembre de 2026. Entrada: `05_plan_owasp.md` suministrado por el equipo.
Base backend: `50a4697`; base frontend: `2ae69fc`. Rama local: `codex/aplicar-plan-owasp`.
Se conserva una etiqueta local `owasp-base-20261119` en cada repositorio.

Este documento registra implementación y comprobaciones locales. No sustituye al
Auditor de Implementación OWASP (paso 8) ni al Auditor Final Integral (paso 9), y no
asigna un nuevo puntaje de seguridad. No acredita cambios en producción.

## Cambios aplicados y activación

| Acción del plan | Implementación | Activación / límite |
|---|---|---|
| A01: acceso protegido en producción | `APP_ENVIRONMENT=production` o `staging` rechaza protección desactivada o credenciales ausentes. Aviso cuando se usa el modo público local. | Configurar el perfil y `PROTECT_DOSSIER_ROUTES=true` en el proveedor. Los valores locales se conservan según el plan. |
| A01/A07: identidad individual | `INDIVIDUAL_ACCOUNTS_ENABLED=true` permite cuentas nominales de `ACADEMIC_ACCOUNTS` fuera de demostración. El expediente nuevo guarda propietario; los antiguos siguen accesibles al revisor de compatibilidad. `/api/sesion` anuncia identidad/acciones sin credenciales. | Roles existentes: administrador, evaluador y responsable. No activa firmas ni modelos simulados fuera de demo. OIDC/BFF sigue siendo una alternativa futura. |
| A07: rotación/caducidad | `REVIEWER_TOKENS` acepta varios tokens con `expires_at` opcional; el token principal admite `REVIEWER_TOKEN_EXPIRES_AT`. Las cuentas individuales también admiten expiración. | Quitar una credencial de la configuración y reiniciar revoca su acceso. Logout continúa eliminando el token de memoria; no se introduce una sesión de servidor. |
| A07: fuerza bruta | Contador acotado por origen y ventana, responde 429 con Retry-After tras el umbral de 401. | `AUTH_RATE_LIMIT_ENABLED=true`; 30 fallos/60 s iniciales. No bloquea `/health`, `/api/capacidades` ni preflight CORS. |
| A04: coste OCR | Cuota por origen y por cuenta autenticada; semáforo de concurrencia compartido entre carga y diagnóstico OCR. | `OCR_LIMITS_ENABLED=true`; 20 solicitudes/60 s, concurrencia 2. Contadores y semáforos son por proceso. |
| A04/A05: diagnósticos | `/health/db` y `/health/ia` requieren revisor cuando `PROTECT_DIAGNOSTICS=true`; OCR cacheado 120 s. Swagger, ReDoc y OpenAPI pueden desactivarse. | `/health` conserva respuesta pública. El conteo de expedientes queda accesible solo a revisores si se activa protección diagnóstica. `scripts/check_server.py` admite token y docs desactivadas. |
| A09: trazabilidad | Registros JSON con ruta registrada, método, estado, actor y UUID válido cuando corresponde; no incluyen token, cabeceras, consulta, nombre de archivo ni OCR. | `SECURITY_EVENTS_ENABLED=true` y `REQUEST_METRICS_ENABLED=true`. El flujo conserva su auditoría existente de cambios de estado. |
| A02: originales cifrados | Fernet autenticado, formato versionado, identidad del expediente ligada al contenido, lectura dual de `.pdf` y `.pdf.enc`, claves múltiples para rotación. Se verifica SHA-256 antes de segmentar cualquier original. | Instalar dependencias opcionales y definir `STORAGE_ENCRYPTION_ENABLED=true`, `STORAGE_ENCRYPTION_KEYS`. No migra originales existentes. El OCR almacenado en BD necesita el cifrado del proveedor. |
| A02: TLS de PostgreSQL | La normalización existente conserva `sslmode=verify-full` y `sslrootcert` si se proporcionan. | Validar CA, hostname y pooler con Supabase antes de modificar la cadena real. No se cambió la conexión de producción. |
| A05: cabeceras | HSTS, nosniff, no-referrer, DENY y CSP en modo solo informe. El BE añade no-store a rutas controladas. Vercel permite explícitamente API y visor blob. | BE: `SECURITY_HEADERS_ENABLED=true`, `HSTS_ENABLED=true` solo tras asegurar HTTPS. FE: reglas en `vercel.json`. CSP no está en bloqueo. |
| A05: higiene | `.env` y `tsconfig.tsbuildinfo` retirados del índice FE; se conserva el archivo local y se documenta `.env.local`. Retirado `MockAuthAdapter` sin consumidores. | No se reescribió el historial. Cualquier secreto histórico real requeriría revocación. |
| A06/A08: dependencias | RapidOCR fijado; dependencias de pruebas separadas; locks Linux/Python 3.12 con hashes para runtime, pruebas y cifrado. | No se cambiaron PyMuPDF, ONNX ni OpenCV. Se corrigieron Certifi, Pillow y Cryptography según el escaneo, conservando pruebas OCR. |
| A06/A08: automatización | Flujos GitHub Actions con acciones fijadas por SHA, pruebas, build, auditoría, escaneo heurístico histórico y Dependabot. FE incluye integración HTTP con BE. | Archivos preparados localmente; se ejecutarán en GitHub después de publicar los commits. La protección de rama requiere configuración del repositorio. |
| A08: recursos | Mismas familias tipográficas autoalojadas con licencias, origen y SHA-256; sin solicitudes Google Fonts desde el HTML/CSS. ZIP ficticio regenerable desde código. | `scripts/verify_assets.py` verifica integridad de fuentes. Paquete de ocho casos proviene de `scripts/academic_examples.py`, no del generador de cuatro casos OCR. |
| A03/A10 | Se conservan validaciones PDF y destinos salientes fijos sin redirecciones. Pruebas de egreso, manipulación de originales y contratos existentes. | No se añadió sandbox al iframe: requiere comprobar visor nativo en Chrome, Edge y Firefox. No se afirma aislamiento duro de CPU/memoria por petición. |

## Instalación y comprobación local

Backend en Linux x86_64/Python 3.12:

```bash
python -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-runtime-linux.lock.txt -r requirements-security-linux.lock.txt -r requirements-test-linux.lock.txt
.venv/bin/pip check
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.build_demo_zip --output /tmp/ejemplos-demo.zip
```

En Windows se conserva `requirements.lock.txt`, que incluye dependencias de
pruebas/cifrado; recrear el entorno. El lock con hashes es específico de Linux
x86_64/Python 3.12 y sus ruedas, no debe usarse como lock universal.
`requirements-dev.txt` permite resolver un entorno de desarrollo sin hashes.

Frontend con Node 24, junto al backend instalado en `../backend`:

```bash
npm ci --ignore-scripts
BACKEND_ROOT=../backend npm test
npm run lint
npm run build
npm audit --audit-level=high
python scripts/verify_assets.py
```

En PowerShell: `$env:BACKEND_ROOT='../backend'` y después `npm test`.
El frontend CI obtiene la rama predeterminada pública del backend: publicar el
backend primero para comprobar la pareja final. No contiene claves del proveedor.

## Rotación y cuentas

`REVIEWER_TOKENS` es una lista JSON de objetos `token` y `expires_at` (fecha ISO
8601 con zona, por ejemplo UTC terminada en Z). El ID de auditoría de esos tokens
sigue siendo `REVIEWER_ID`. Añadir el nuevo, distribuirlo por canal seguro y luego
retirar el anterior. Para identidad diferenciada usar cuentas individuales.

`ACADEMIC_ACCOUNTS` conserva su nombre para compatibilidad y admite objetos con
`id`, `role`, `token`, `department` (solo responsable) y `expires_at` opcional.
Los identificadores empiezan por letra minúscula y usan letras, números, guion o
subrayado; los tokens tienen al menos 32 caracteres. Las áreas de responsables
son las del catálogo TUPA. Con `ACADEMIC_DEMO=false` y la bandera individual activa
no se exige marca ficticia, pero los datos reales siguen sujetos a las validaciones
operativas pendientes que se enumeran abajo. No migrar ni reasignar propietarios
antiguos automáticamente. Conservar tokens de compatibilidad solo durante la
transición acordada.

## Cifrado, persistencia y reversión

Generar claves Fernet fuera de git y guardarlas en el gestor de secretos. La
primera cifra archivos nuevos; las restantes permiten leer claves anteriores.
No perder claves: la pérdida hace irrecuperables los originales cifrados.
Para volver a escribir sin cifrar, desactivar `STORAGE_ENCRYPTION_ENABLED`, pero
conservar claves y dependencia para leer `.pdf.enc`. Restaurar el código previo
solo después de disponer de una restauración compatible: ese código no lee cifrado.
No hay migración ni borrado de datos reales en este cambio.

Los nuevos originales usan permisos de archivo 0600. Los PDF heredados siguen
legibles. Un original alterado, intercambiado entre expedientes o cifrado con clave
incorrecta se rechaza. El directorio debe ser persistente y exclusivo de la
aplicación. La BD conserva el JSON/OCR en su formato previo: el cifrado opcional
de originales no cifra ese contenido ni los respaldos del proveedor.

## Límites y trabajo operativo pendiente

1. Revisar variables y publicar por etapas BE antes que FE; usar
   `.env.production.example` como lista de variables, sin reemplazar ni exponer
   las credenciales actuales. Activar controles uno por vez y observar tasas de error.
2. Respaldar Supabase y originales, probar restauración y verificar cifrado de
   discos, BD y respaldos con el proveedor. No se accedió a cuentas Render/Vercel/Supabase.
3. Rotar y entregar tokens reales; verificar que las cuentas nominales, roles y
   áreas coinciden con el negocio. No se distribuyeron credenciales ni mensajes.
4. Los límites por proceso complementan el proxy. Para varios workers/réplicas,
   configurar límite compartido en el borde/Redis; comprobar IP resuelta por Uvicorn
   y su lista de proxies confiables. No confiar en X-Forwarded-For arbitrario ni
   activar encabezados reenviados desde cualquier IP. Ajustar umbrales para NAT
   compartido tras observar registros.
5. No existe un límite duro de tiempo/memoria por OCR: las cuotas/concurrencia
   reducen carga, pero un documento hostil puede agotar un worker. Completar
   aislamiento de procesos/cgroups y límites del proveedor antes de datos reales.
6. Configurar alertas del proveedor: ráfagas de 401/429, aumentos de 5xx y accesos
   fuera de horario; definir destinatarios, retención y acceso a logs. No se afirma
   que esas alertas ya estén funcionando.
7. Política de retención pendiente de decisión del negocio. No se implementó ni
   ejecutó borrado automático de expedientes u originales.
8. Validar `verify-full` contra Supabase con su CA/hostname reales; no basta con
   una prueba local de normalización para acreditar TLS en producción.
9. CSP queda en solo informe: probar visor, descarga, fuentes y navegación real
   en Chrome, Edge y Firefox antes de bloqueo. El intento local de Chromium no
   pudo arrancar por restricciones del entorno; no se acredita revisión visual.
   Si cambia el dominio de API, ajustar `connect-src` de Vercel explícitamente.
10. Habilitar protección de rama/revisión obligatoria en GitHub; publicar los
    workflows para ejecutar CI real. El escáner histórico detecta formatos conocidos
    de claves y no constituye una búsqueda infalible de secretos arbitrarios.
11. Los criterios de cierre del plan (score >=80, controles activos en producción,
    CSP en bloqueo y aceptación de riesgos) permanecen sujetos a pasos 8/9 y
    verificaciones operativas. No declarar esos criterios cumplidos con pruebas locales.

## Modelo de amenazas breve

| Actor / frontera | Datos o riesgo | Control y riesgo residual |
|---|---|---|
| Navegador - API pública | Tokens, PDFs y OCR; fuerza bruta y lectura indebida | HTTPS del proveedor, token en memoria, autorización BE, cuotas, cabeceras. Token robado sirve hasta expiración/revocación. |
| Evaluador - otro expediente | Acceso a expediente ajeno o asignación indebida | Propietario/rol/unidad verificados en BE. Compatibilidad antigua necesita migración acordada. |
| PDF no confiable - OCR nativo | CPU/memoria, parsers y archivos manipulados | Tamaño/páginas/DPI, cuotas, concurrencia, dependencias corregidas y SHA-256. Falta aislamiento duro por trabajo. |
| Aplicación - disco/BD/respaldo | DNI/RUC y originales | Cifrado opcional de PDF y permisos; cifrado BD/discos y backups por verificar con proveedores. |
| Aplicación - IA externa | Filtración o egreso a destinos controlados por atacante | Hosts fijos, sin redirecciones, hechos minimizados y políticas existentes; sin credenciales en FE. |
| Git/CI/recursos externos | Dependencias o recursos alterados | Acciones por SHA, locks/hashes, escaneos, fuentes locales; configuración de protección de rama pendiente. |

Aprobar uso con datos reales requiere responsables para riesgo residual,
retención, restauración, alertas y verificación del despliegue. Este cambio no
introduce nuevas integraciones municipales ni acredita firma legal.


## Evidencia local de esta ejecución

- Línea base: 166 pruebas BE y 51 FE, incluida integración HTTP real.
- Resultado tras controles y actualización de dependencias: 181 pruebas BE y 53 FE;
  comprobaciones TypeScript y build Vite satisfactorios. Dos avisos de deprecación
  Starlette/AnyIO ya presentes en la línea base.
- `pip check` satisfactorio y reinstalación de los tres locks Linux con
  `--require-hashes` en un entorno separado.
- `pip-audit` final: sin vulnerabilidades conocidas en los 42 paquetes de runtime
  y cifrado auditados. `npm audit` final: cero avisos. Son resultados de la fuente
  de avisos consultada, no garantía de ausencia de vulnerabilidades.
- Dependencias corregidas: Certifi 2026.7.22 -> 2026.10.18;
  Pillow 12.3.0 -> 13.0.0; cifrado opcional Cryptography 48.0.1 -> 50.0.0.
  Los reportes JSON antes/después están en `docs/evidencias_owasp/` de cada repo.
- Escaneo heurístico del historial disponible: 338 objetos BE y 366 FE antes de
  estos commits, sin coincidencias de los formatos de credenciales comprobados.
  No cubre secretos de formato arbitrario, ramas remotas no descargadas ni cuentas
  del proveedor. No justifica afirmar ausencia total de secretos.
- Integridad de fuentes locales y regeneración del ZIP ficticio verificadas.
- No se completó inspección visual automatizada: Chromium del entorno no pudo
  iniciarse por restricción de sockets. Quedan pendientes visor, fuentes y CSP
  en Chrome/Edge/Firefox sobre staging, y la prueba de carga acotada del proveedor.
- Flujos CI y Dependabot preparados; no se confunde ejecución local con ejecución
  de GitHub Actions. No hubo push, despliegue, rotación real, acceso a datos
  de ciudadanos ni modificación de variables externas.

La comparación de las cuatro muestras OCR del código base (Pillow 12.3.0) con
el código actualizado (Pillow 13.0.0) produjo resultados idénticos: texto, método,
confianza, DPI y tipos de error. Incluye PDF digital, escaneado, baja resolución
y página vacía. Esto verifica las muestras sintéticas, no todos los documentos posibles.
