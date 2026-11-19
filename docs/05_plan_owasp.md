# 05 — Plan de Remediación OWASP Top 10

**Entrada:** `04_Auditoria_OWASP.md` (score 58/100; 0 críticos, 4 altos, 4 medios, 2 bajos).
**Repositorios:** `ExpedientesMuniFront` (FE) y `Back-End-TP` (BE).
**Naturaleza:** documento de planificación. No contiene código ni modifica los repositorios.
**Meta de score:** ≥ 80/100 tras las fases 1–3, sin cambios en procesos de negocio.

---

## 1. Principios para no romper funcionalidad

Estas reglas aplican a todas las acciones del plan.

1. **Cambios aditivos y detrás de bandera.** Todo control nuevo se activa por variable de entorno, con un valor inicial que reproduce el comportamiento actual. Se activa primero en pruebas/staging, luego en producción y por último se convierte en valor por defecto.
2. **Contrato HTTP intocable.** No se renombran rutas, campos ni códigos de estado existentes. `/health` (usado por el health check de Render) y `/api/capacidades` (el FE lee `seguridad.expedientes_protegidos`, `seguridad.roles_academicos` y `demo` antes del login) deben conservar esos campos.
3. **Orden FE ↔ BE.** El BE se despliega primero y debe aceptar el comportamiento antiguo y el nuevo. El FE actual ya exige protección activada, así que endurecer el BE no lo rompe.
4. **Red de seguridad de pruebas.** Antes de tocar nada, se congela como línea base la suite actual (la documentación indica ~67 pruebas BE y ~34 FE) y se ejecuta en cada cambio. Los controles nuevos añaden pruebas; no sustituyen las existentes.
5. **Una mitigación por despliegue**, con etiqueta de git previa, para poder revertir de forma aislada.
6. **Respaldo previo** de base de datos (Supabase) y del directorio de originales antes de cualquier cambio que toque datos o almacenamiento.
7. **Modo local/demostración preservado.** Los scripts (`scripts/*`), el lanzador académico y las pruebas siguen funcionando con valores por defecto de desarrollo; el endurecimiento por defecto se aplica solo a producción mediante perfil/aviso.

---

## 2. Orden recomendado (resumen)

| Fase | Plazo | Contenido | Riesgo de ruptura |
|---|---|---|---|
| **0** Verificación y línea base | Semana 0 | Confirmar config real de producción; congelar pruebas; respaldos; entorno de staging | Nulo |
| **1** Configuración y bajo riesgo | Semanas 1–2 | A01 (producción), A09 (activar métricas), A05 parcial, A06/A08 en CI, higiene de repos | Bajo |
| **2** Endurecimiento de acceso | Semanas 3–5 | A07 (límite de intentos, caducidad opcional), A04 (límites y `/health/ia`), A09 (auditoría de accesos), A05 (cabeceras) | Medio |
| **3** Estructural | Semanas 6–10 | A02 (cifrado en reposo), A01/A07 (tokens por persona, OIDC/BFF), A08 (hashes, SRI/autoalojado) | Medio-Alto |
| **4** Sostenimiento | Continuo | Escaneo recurrente, revisión de logs, pruebas dinámicas, A10 | Bajo |

Dependencias clave: **Fase 0 → todo**; **A09 (registro) antes de A07/A04** para poder medir el efecto de los límites y detectar falsos positivos; **A06 (CI con pruebas)** antes de cualquier cambio de dependencias o de cabeceras; **A01 en producción** no depende de código y se puede hacer ya.

---

## 3. Plan por vulnerabilidad

Formato: Riesgo · Prioridad · Impacto · Componentes · Mitigación · Validación · Rollback.

### A01 — Broken Access Control · **Alto** · Prioridad 1

- **Riesgo:** con `PROTECT_DOSSIER_ROUTES=false` (valor por defecto) la carga, consulta y descarga de segmentos no exigen credencial; fuera del modo académico no hay autorización por expediente.
- **Impacto:** exposición de datos personales (DNI/RUC) de expedientes.
- **Componentes:** BE `settings.py`, `academic_access.py`, `controllers/`; configuración de Render; FE `ApiAuthAdapter` (ya exige protección).
- **Mitigación:**
  1. *(Inmediata, sin código)* Verificar y fijar `PROTECT_DOSSIER_ROUTES=true` en producción y staging, con `REVIEWER_TOKEN`/`REVIEWER_ID` válidos. El FE desplegado ya requiere este modo, por lo que no hay cambio funcional.
  2. Añadir un **aviso al arrancar** (o negativa a arrancar si se define una variable de entorno de "producción") cuando la protección esté desactivada; el modo local sigue permitido de forma explícita.
  3. Cambiar el valor por defecto a protegido **solo después** de actualizar pruebas, scripts y README; mantener la posibilidad de desactivarlo explícitamente para desarrollo local.
  4. *(Fase 3)* Asociar cada expediente a un propietario/unidad también fuera del modo académico, de forma aditiva: expedientes existentes sin propietario siguen visibles para el revisor actual hasta migrarlos.
- **Validación:** prueba de contrato "sin token → 401 en POST/GET de expedientes y descarga"; "con token válido → 200/201 idéntico al actual"; suite FE de integración con el servidor de soporte (`support_frontend_server.py`); comprobación manual con el flujo de carga-consulta-descarga en staging.
- **Rollback:** restaurar la variable de entorno anterior (cambio de configuración, sin redeploy de código); si se cambió el valor por defecto, revertir ese commit aislado.

### A07 — Authentication Failures · **Alto** · Prioridad 2

- **Riesgo:** token compartido sin caducidad ni revocación individual; sin límite de intentos fallidos; logout solo en cliente.
- **Impacto:** compromiso de un único secreto da acceso total; fuerza bruta en línea posible.
- **Componentes:** BE `security.py`, `academic_access.py`, `settings.py`; FE `ApiClient`, `ApiAuthAdapter`, `LoginScreen`.
- **Mitigación (escalonada):**
  1. **Inmediata:** rotar el token actual con valor aleatorio largo y entregarlo por canal seguro; documentar calendario de rotación.
  2. **Límite de intentos por origen** para respuestas 401, con umbrales holgados y respuesta 429 (el FE ya muestra un mensaje genérico ante errores HTTP). Preferible aplicarlo en el borde (proxy/Render) antes que en código de aplicación.
  3. **Caducidad opcional**: soporte aditivo para tokens/cuentas con fecha de expiración y varios tokens simultáneos para rotar sin corte; el token único actual sigue funcionando.
  4. **Cuentas individuales:** extender el mecanismo de `ACADEMIC_ACCOUNTS` (ya existente) a uso no demostrativo, o migrar a OIDC con PKCE / BFF con cookies HttpOnly (propuesta ya documentada en `DEPLOYMENT.md`).
  5. Retirar `MockAuthAdapter` (`admin/admin`) del código exportado una vez confirmado que ninguna prueba ni composición lo usa.
- **Validación:** pruebas de 401/429/403; verificación de que token vigente sigue autenticando; prueba de rotación con dos tokens activos; prueba de que el FE sigue funcionando sin cambios con el token actual; búsqueda de referencias a `MockAuthAdapter` antes de eliminarlo.
- **Rollback:** desactivar el límite y la caducidad por variable; mantener el token anterior válido durante una ventana de convivencia; el paso OIDC/BFF se despliega en paralelo y se retira sin afectar al token estático mientras conviva.

### A04 — Insecure Design · **Alto** · Prioridad 3

- **Riesgo:** diseño de secreto único; valor por defecto abierto; endpoints costosos (OCR) sin cuotas, incluido `/health/ia` sin autenticación.
- **Impacto:** denegación de servicio por consumo de CPU; auditoría sin identidad personal; retención indefinida de PII.
- **Componentes:** BE `main.py` (`/health/ia`, `/health/db`), `controllers/`, `ocr.py`, `settings.py`; infraestructura Render.
- **Mitigación:**
  1. **`/health/ia`:** exigir credencial de revisor o limitar su frecuencia y almacenar en caché el resultado unos minutos. Mantener `/health` público sin cambios porque Render lo usa. Antes de cambiar, revisar quién consume `/health/ia` y `/health/db` (p. ej. `scripts/check_server.py`) y ajustar esos consumidores.
  2. **Cuotas de carga:** límite de tasa y de concurrencia de OCR por origen/cuenta; conservar los límites actuales de tamaño y páginas (20 MB/30 págs.), que son compatibles.
  3. **Política de retención y borrado** de expedientes y originales (definir con el negocio; no ejecutar borrados automáticos hasta aprobarla).
  4. Documentar un **modelo de amenazas** breve (actores, datos, fronteras) como criterio de aceptación para pasar de demostración a datos reales.
- **Validación:** prueba de carga acotada en staging confirmando que el tráfico legítimo de evaluadores no recibe 429; pruebas de que `/health` sigue respondiendo 200 sin credencial; revisión de scripts.
- **Rollback:** bandera de configuración para los límites; revertir el cambio de acceso a `/health/ia` si algún consumidor externo dependía de él.

### A09 — Logging and Monitoring Failures · **Alto** · Prioridad 2 (habilitador)

- **Riesgo:** métricas apagadas; no se registran intentos fallidos, lecturas ni descargas de expedientes.
- **Impacto:** accesos indebidos a PII indetectables y no reconstruibles.
- **Componentes:** BE `metrics.py`, `academic_access.py`, `security.py`, controladores; Render (logs).
- **Mitigación:**
  1. **Inmediata:** activar `REQUEST_METRICS_ENABLED=true` en producción (ya existe, no registra datos sensibles).
  2. Añadir **eventos de seguridad estructurados**: autenticación fallida/exitosa (identificador de actor, nunca el token), lectura/descarga/carga de expediente (ID de expediente, actor, resultado), cambios de rol/estado. Sin texto OCR, DNI ni cabeceras.
  3. Definir **alertas mínimas** (ráfagas de 401, picos de 5xx, accesos fuera de horario) sobre los logs del proveedor.
  4. Definir retención y acceso a los logs.
- **Validación:** pruebas que verifican que los eventos se emiten y que **no** contienen tokens ni PII; revisión de una muestra de logs en staging; confirmar que la latencia no se degrada de forma apreciable.
- **Rollback:** desactivar por variable; los registros adicionales no alteran respuestas HTTP.

### A02 — Cryptographic Failures · **Medio** · Prioridad 4

- **Riesgo:** PDFs y texto OCR sin cifrado a nivel de aplicación; tokens estáticos de larga vida; `sslmode=require` sin verificación de certificado; sin HSTS.
- **Impacto:** exposición de PII ante acceso al disco, copia de BD o respaldo.
- **Componentes:** BE `storage.py`, `database.py`, `settings.py`; Supabase; disco persistente de Render.
- **Mitigación:**
  1. Confirmar **cifrado en reposo del proveedor** (disco de Render y Supabase) y documentarlo; es el paso de menor riesgo.
  2. Pasar la conexión a PostgreSQL a **verificación de certificado** (`verify-full`) tras comprobar que el pooler de Supabase lo admite.
  3. Añadir **HSTS** en el borde (ver A05).
  4. *(Fase 3, opcional según riesgo aceptado)* Cifrado de originales a nivel de aplicación con **formato versionado y lectura dual** (lee cifrado y sin cifrar), migración gradual y clave fuera del repositorio. Los archivos existentes siguen legibles.
- **Validación:** pruebas de lectura de archivos antiguos y nuevos; prueba de conexión a BD con verificación en staging; restauración de un respaldo cifrado en entorno de prueba.
- **Rollback:** el modo de lectura dual permite volver a escribir sin cifrar; conservar copia previa de los originales hasta confirmar la migración; la verificación de certificado se revierte con la cadena de conexión anterior.

### A05 — Security Misconfiguration · **Medio** · Prioridad 3

- **Riesgo:** `/docs`, `/openapi.json`, `/health/db` (revela cantidad de expedientes), `/health/ia` y `/api/capacidades` públicos; sin cabeceras de seguridad; `.env` y `tsbuildinfo` versionados en el FE.
- **Impacto:** reconocimiento facilitado; superficie de clickjacking/XSS sin CSP.
- **Componentes:** BE `main.py`, `municipal.py`; FE `vercel.json`, `index.html`, `.gitignore`; Vercel/Render.
- **Mitigación:**
  1. **`/health/db`:** quitar el conteo de la respuesta pública (o proteger la ruta). **`/docs`/`openapi`:** desactivar o proteger en producción mediante bandera. **No** retirar campos de `/api/capacidades` que el FE consume; solo ocultar los no usados (p. ej. proveedor/modelo de IA) tras verificar que el FE no los lee.
  2. **Cabeceras de seguridad** en Vercel y en el BE: HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`/`frame-ancestors`. Introducir la **CSP primero en modo solo-informe** (`Report-Only`). La CSP debe permitir explícitamente: Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`) mientras no se autoalojen, el origen de la API, `frame-src`/`object-src` para el visor PDF basado en `blob:`, y los recursos de Swagger si `/docs` queda habilitado.
  3. **Higiene:** dejar de versionar `.env` y `tsconfig.tsbuildinfo` (quitarlos del índice, no del disco); asegurar que Vercel/entornos usan `VITE_API_URL` desde sus variables y que `.env.example` documenta el paso para desarrolladores.
  4. Evaluar `sandbox` del `<iframe>` del visor **solo si** el visor PDF nativo del navegador sigue funcionando (muchos navegadores no muestran su visor en iframes con sandbox).
- **Validación:** navegación completa del FE en staging con CSP en modo informe y revisión de violaciones antes de pasar a modo bloqueo; prueba del visor PDF y de descarga en Chrome, Edge y Firefox; verificación de que las pruebas del FE y el login siguen en verde.
- **Rollback:** las cabeceras se revierten en `vercel.json`/configuración BE; la CSP vuelve a modo informe; las rutas ocultas se reactivan por bandera.

### A06 — Vulnerable and Outdated Components · **Medio** · Prioridad 2 (CI)

- **Riesgo:** no verificado; `rapidocr-onnxruntime` sin versión en `requirements.txt`; `pytest` mezclado con dependencias de ejecución; lock generado en Windows y despliegue en Linux; sin automatización de actualizaciones.
- **Impacto:** vulnerabilidades conocidas no detectadas en librerías con gran superficie nativa (OpenCV, ONNX, PyMuPDF).
- **Componentes:** BE `requirements*.txt`; FE `package.json`/`package-lock.json`; repositorios (sin CI).
- **Mitigación:**
  1. **Ejecutar con red** `pip-audit` y `npm audit` ahora y registrar el resultado como línea base.
  2. Crear **CI** (que hoy no existe) que ejecute las suites existentes, `tsc`/build y los escaneos en cada PR.
  3. Activar **Dependabot/Renovate** con PRs pequeños; actualizar solo parches/menores con la suite en verde.
  4. Separar dependencias de desarrollo y fijar `rapidocr-onnxruntime`; regenerar el lock en Linux/Python 3.12 y comparar versiones resueltas con el actual antes de adoptarlo.
- **Validación:** suite completa BE/FE en CI; `/health/ia` y la carga de PDFs sintéticos en staging para detectar regresiones de OCR; comparación de resultados OCR antes/después en los PDFs de demostración.
- **Rollback:** conservar el lock anterior en una etiqueta; revertir el PR de actualización; no actualizar `onnxruntime`/`opencv`/`pymupdf` junto con otros cambios.

### A08 — Software and Data Integrity Failures · **Medio** · Prioridad 4

- **Riesgo:** sin CI ni verificación de integridad; sin hashes en dependencias Python; recursos de terceros sin SRI; binario `ejemplos-demo.zip` versionado.
- **Impacto:** compromiso de la cadena de suministro o de recursos externos.
- **Componentes:** repos FE/BE; `index.html`; `public/ejemplos-demo.zip`; lockfiles.
- **Mitigación:**
  1. CI y escaneo (ver A06) con protección de rama y revisión obligatoria.
  2. **Autoalojar** las fuentes (misma tipografía, sin cambio visual) o añadir SRI donde aplique; esto además simplifica la CSP.
  3. Instalación con **verificación de hashes** (`--require-hashes`) una vez regenerado el lock en Linux.
  4. Documentar el origen del ZIP de ejemplos y regenerarlo desde `scripts/create_demo_pdfs.py` en CI; confirmar que sigue marcando "EXPEDIENTE FICTICIO".
- **Validación:** compilación reproducible en CI; comparación visual de la interfaz con fuentes autoalojadas; la prueba de demostración que carga los PDFs del ZIP.
- **Rollback:** volver al `<link>` de Google Fonts; quitar `--require-hashes` en el comando de build; restaurar el ZIP anterior desde git.

### A03 — Injection · **Bajo** · Prioridad 5

- **Riesgo:** residual — procesamiento de PDFs no confiables con librerías nativas; `<iframe>` sin sandbox; prompt injection hacia el LLM (ya mitigada).
- **Impacto:** bajo; sin vector concreto identificado.
- **Componentes:** BE `ocr.py`, `pdf_segments.py`, adaptadores de IA; FE `DocumentPreview.tsx`.
- **Mitigación:** mantener validaciones actuales; ejecutar el OCR con límites de tiempo/memoria y mantener actualizadas las librerías (A06); revisar el sandbox del iframe junto con A05; añadir pruebas con PDFs malformados.
- **Validación:** pruebas con PDFs corruptos/protegidos/de gran tamaño; confirmar que los errores 400/422 existentes no cambian.
- **Rollback:** los límites se controlan por configuración; revertir el cambio del iframe.

### A10 — SSRF · **Bajo** · Prioridad 6

- **Riesgo:** mínimo; llamadas salientes a hosts fijos y sin redirecciones.
- **Mitigación:** conservar el diseño; añadir una prueba de regresión que falle si alguna llamada saliente acepta una URL derivada de la entrada; si algún día se aceptan URLs o modelos desde la petición, añadir lista de destinos permitidos.
- **Validación:** revisión de código en cada PR que añada clientes HTTP.
- **Rollback:** no aplica (sin cambio).

---

## 4. Roadmap de remediación

**Fase 0 — Semana 0 (sin cambios de código)**
- Confirmar variables reales de Render/Vercel/Supabase (A01, A05).
- Ejecutar `pip-audit`/`npm audit` con red y búsqueda de secretos en todo el historial de git (A06, A05).
- Congelar y documentar la línea base de pruebas; crear staging; respaldar BD y originales; etiquetar versiones actuales.

**Fase 1 — Semanas 1–2 (riesgo bajo)**
- Producción con `PROTECT_DOSSIER_ROUTES=true` y rotación del token (A01, A07).
- Activar `REQUEST_METRICS_ENABLED` (A09).
- Crear CI con pruebas y escaneos; activar Dependabot (A06, A08).
- Retirar `.env`/`tsbuildinfo` del control de versiones; fijar `rapidocr-onnxruntime` y separar dependencias de desarrollo (A05, A06).
- Ocultar conteo en `/health/db`; decidir sobre `/docs` (A05).

**Fase 2 — Semanas 3–5**
- Límite de intentos y tasa en el borde; `/health/ia` protegido o con caché (A07, A04).
- Eventos de seguridad estructurados y alertas mínimas (A09).
- Cabeceras de seguridad y CSP en modo informe → bloqueo (A05).
- Aviso/negativa de arranque inseguro en producción; luego cambio del valor por defecto (A01).

**Fase 3 — Semanas 6–10**
- Tokens con caducidad y múltiples tokens para rotación; diseño e implementación de identidad individual (OIDC/BFF) (A07, A01).
- Verificación de certificado de BD, HSTS, cifrado de originales con lectura dual (A02).
- Autoalojar fuentes/SRI; hashes de dependencias (A08).
- Política de retención aprobada por el negocio (A04).

**Fase 4 — Continuo**
- Revisión de logs y alertas; actualizaciones de dependencias; pruebas dinámicas (fuerza bruta, PDFs maliciosos); re-auditoría OWASP al cierre de cada fase.

---

## 5. Riesgos de implementación

| Riesgo | Probabilidad | Efecto | Mitigación |
|---|---|---|---|
| Cambiar el valor por defecto de protección rompe pruebas, scripts o clientes locales | Alta | Medio | Hacerlo después de actualizar pruebas/README; mantener opción explícita de desactivar |
| Límite de intentos bloquea a evaluadores legítimos (p. ej. tras NAT compartido) | Media | Medio | Umbrales holgados, medir primero con registros (A09), activar por bandera |
| CSP bloquea fuentes, visor PDF o Swagger | Alta | Medio | Modo solo-informe primero; pruebas en 3 navegadores |
| `sandbox` del iframe deshabilita el visor PDF del navegador | Media | Medio | Probar antes; mantener sin sandbox si afecta al visor |
| Cierre de `/health/db`/`/health/ia` rompe monitores o scripts | Media | Bajo | Inventariar consumidores antes del cambio |
| Ocultar campos de `/api/capacidades` rompe el FE antes del login | Media | Alto | No retirar campos usados por el FE; prueba de contrato |
| Actualización de dependencias altera resultados de OCR | Media | Alto | Comparar salidas sobre PDFs de demostración; actualizar de a una librería |
| Lock regenerado en Linux cambia versiones y comportamiento | Media | Medio | Comparación previa y despliegue en staging |
| Cifrado de originales corrompe o hace ilegibles archivos | Baja | Alto | Lectura dual, copia previa, migración por lotes con verificación SHA-256 |
| Cambio de autenticación interrumpe a usuarios actuales | Media | Alto | Convivencia de token antiguo y nuevo; despliegue en paralelo |
| Quitar `.env` del repo deja sin configuración a desarrolladores | Media | Bajo | `.env.example` actualizado y aviso en README |
| Sobrecarga de logs o registro accidental de PII | Baja | Alto | Pruebas que verifican ausencia de tokens/PII en logs |

---

## 6. Estrategia para preservar funcionalidad

1. **Pruebas de contrato antes y después.** Para cada cambio se comparan respuestas de los endpoints existentes (estado y forma de la respuesta) en `/api/capacidades`, carga, consulta, flujo, validación, borradores, enrutamiento, asignación e indicadores. Cualquier diferencia no prevista bloquea la fusión.
2. **Reutilizar las suites existentes** (BE: OCR real, persistencia, concurrencia TUPA, autenticación, CORS; FE: integración HTTP real contra la fábrica FastAPI) como puerta de calidad y ampliarlas solo con casos nuevos.
3. **Banderas de configuración y valores iniciales equivalentes** al comportamiento actual; el endurecimiento se activa de forma gradual: staging → producción → valor por defecto.
4. **Recorridos de negocio de referencia** en staging tras cada fase: iniciar sesión → cargar PDF de demostración → consultar expediente → verificar guardado → revisión TUPA (incluido el conflicto 409) → borrador → enrutamiento/asignación → descarga de segmentos → cierre de sesión. Se repite con los roles de demostración (administrador, evaluador, responsable).
5. **Compatibilidad hacia atrás explícita:** el token actual sigue siendo válido durante todas las migraciones; los expedientes y originales existentes siguen accesibles; los esquemas de BD no cambian sin migración reversible.
6. **Despliegues pequeños y reversibles:** un cambio por vez, versión etiquetada, respaldo previo, ventana de observación con las métricas de A09 y criterio de reversión definido (aumento de 4xx/5xx, caída de la tasa de éxito de carga).
7. **Comunicación:** avisar a los evaluadores antes de rotar el token o activar límites; mantener canal de soporte durante la primera semana de cada fase.

## 7. Criterios de cierre

- Producción con protección activa, token rotado y límites de intentos vigentes.
- Registro y alertas de seguridad operando, sin PII en logs.
- CI con pruebas y escaneo de dependencias sin hallazgos altos/críticos abiertos.
- Cabeceras de seguridad y CSP en bloqueo sin regresiones en el visor PDF.
- Política de retención aprobada y modelo de amenazas documentado.
- Re-auditoría OWASP con score ≥ 80 y 0 hallazgos Altos sin plan aceptado.
