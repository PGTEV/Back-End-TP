# Integración React y despliegue

## Aplicación correcta y compatibilidad

El backend correcto es [PGTEV/Back-End-TP](https://github.com/PGTEV/Back-End-TP), auditado sobre `881466515db6a30ff713e8902bb51828a8066480`. La integración React usa la arquitectura hexagonal de `src/infrastructure/main.py`, con persistencia SQL, almacenamiento original, OCR y flujo TUPA. Arranque:

```sh
uvicorn src.infrastructure.main:create_app --factory --host 0.0.0.0 --port $PORT
```

En PowerShell local, reemplazar `$PORT` por `8000` y usar `--host 127.0.0.1`. Este repositorio no contiene `src/main.py`; la aplicación alternativa descrita en la auditoría inicial pertenecía al repositorio indicado por error y no aplica aquí. Se conservan `/health/db`, `/health/ia` y la normalización de conexiones Supabase/PostgreSQL. Se puede comprobar el arranque correcto mediante `/api/capacidades`, `/docs` y `/openapi.json`.

Se añadió `PROTECT_DOSSIER_ROUTES` (por defecto false para preservar los clientes locales). Cuando es true, exige el Bearer de revisor en POST/GET de expedientes y GET del catálogo. Las rutas de flujo ya exigían esta credencial y mantienen esa protección. `/health` y `/api/capacidades` siguen públicos. El único cambio de respuesta existente es el campo aditivo `seguridad` de capacidades. No hay endpoints nuevos ni cambios de esquema SQL ni migraciones de datos.

No existe edición de campos de extracción. La carga ya escribe en SQL y disco. Se añadió descarga de segmentos originales mediante `GET /api/expedientes/{id}/documentos/{index}/pdf`, con la protección de expedientes y sin tokens en URLs; requiere que el original siga disponible. La revisión TUPA es otra escritura real, con control optimista `revision`, auditoría e identidad fijada por el servidor.

## Render

1. Incorporar estos cambios a `PGTEV/Back-End-TP` antes de actualizar el frontend. El backend desplegado es https://back-end-tp.onrender.com y el frontend es https://expedientes-muni-front.vercel.app. Conservar las variables actuales de conexión y almacenamiento.
2. Python 3.12. Build `pip install -r requirements.lock.txt`. Arranque con el comando de fábrica anterior. Health check `/health`. En el repositorio independiente la raíz es `.`; en esta copia es `backend-render`.
3. Configurar estas variables en el servidor:

```dotenv
PROTECT_DOSSIER_ROUTES=true
REVIEWER_ID=evaluador-prototipo
CORS_ORIGINS=["https://expedientes-muni-front.vercel.app"]
# Mantener DATABASE_URL de Supabase si ya está configurada; no sustituirla por SQLite.
# Solo para una instalación nueva con SQLite y disco montado:
# DATABASE_URL=sqlite:////var/data/expedientes.db
STORAGE_DIR=/var/data/originales
```

Configurar también **REVIEWER_TOKEN** con un valor aleatorio privado de al menos 32 caracteres, generado fuera del código y entregado al evaluador por un canal seguro. No copiarlo a VITE, Git, documentación, logs ni capturas. El token compartido no es una clave pública de aplicación; quien lo conoce puede consultar todos los expedientes protegidos de este prototipo.

4. Para SQLite y originales, montar un disco persistente en `/var/data`. Sin ese disco, el almacenamiento local se pierde en reinicios y despliegues. Los discos persistentes tienen restricciones de escalado y están disponibles en servicios pagados; consultar [Render: discos persistentes](https://render.com/docs/disks). PostgreSQL puede reemplazar SQLite con una URL SQLAlchemy `postgresql+psycopg://...`, pero los originales siguen necesitando disco u otro adaptador de almacenamiento. Cambiar DATABASE_URL no migra los registros existentes. Respaldar BD y originales antes de cambiar rutas/proveedor; un disco nuevo no recupera los archivos del almacenamiento efímero anterior.
5. Configurar los dominios exactos en CORS sin rutas ni barra final. GET/POST y los headers Content-Type/Authorization ya están permitidos; CORSMiddleware responde a OPTIONS. No se requieren cookies ni `allow_credentials` para este cliente Bearer. CORS no autoriza usuarios; las peticiones fuera del navegador siguen necesitando control de acceso. [FastAPI: CORS](https://fastapi.tiangolo.com/tutorial/cors/).
6. Publicar después el frontend con su `VITE_API_URL` HTTPS y reconstruirlo. Ver `../frontend/README.md` en esta copia de trabajo.

## Comprobación tras desplegar

Con un PDF sintético y una credencial válida, sin exponerla en capturas/logs:

- `/health` responde 200; capacidades anuncia `seguridad.expedientes_protegidos=true`.
- Catálogo sin token devuelve 401; con token devuelve 200. Credencial del servidor ausente o mal configurada devuelve 503.
- Desde Vercel, el preflight autoriza su origen exacto y headers. Un origen no incluido no recibe Access-Control-Allow-Origin.
- Subir el PDF devuelve 201, UUID, SHA-256 y documentos; consultar por ID devuelve la misma extracción.
- «Verificar guardado en BD» confirma la copia; consultar el ID después de un reinicio conserva el resultado. Comprobar también los originales en el disco configurado.
- Revisar TUPA devuelve una revisión nueva y mantiene PENDIENTE_REVISION hasta completar revisión humana; enviar una revisión antigua devuelve 409. Una confianza OCR alta no acredita cumplimiento normativo.
- El visor muestra el archivo cargado y permite descargarlo. Una consulta posterior conserva la extracción y permite descargar sus segmentos originales autorizados si permanecen en el almacenamiento.

Se verificó la instalación anterior mediante GET/OPTIONS: frontend, health y capacidades responden, el contrato coincide y el preflight CORS autoriza el origen real. No se subieron archivos a producción ni se consultaron expedientes reales. No hay acceso a los paneles para comprobar las variables, el commit vinculado o el disco. La versión corregida se prueba localmente con Python 3.12 y las versiones bloqueadas; no se probó una conexión real a Supabase ni Linux/Render.

## Autenticación segura propuesta para una publicación municipal

La protección añadida corrige el acceso simulado y limita las rutas del prototipo, pero no resuelve usuarios individuales. Antes de expedientes reales:

- Integrar un proveedor OIDC con flujo de autorización y PKCE, o un BFF con sesión en cookies HttpOnly/Secure y protección CSRF. No guardar un secreto de aplicación en una SPA ni tokens duraderos en localStorage.
- Validar en el backend emisor, audiencia, firma, caducidad y permisos; obtener la identidad del token/sesión validada. Incorporar roles y acceso por expediente/unidad; nunca confiar en el alias enviado por React para auditoría.
- Añadir expiración, revocación, rotación, límites de intentos/carga, auditoría de accesos y controles de privacidad. El token actual no tiene caducidad ni revocación individual y se rota mediante configuración del servidor.
- Si se requiere editar campos, acordar primero el contrato de actualización con validación, autorización y control de versión. Si se requiere recuperar PDFs, añadir un puerto de lectura y un caso de uso de descarga con autorización por expediente. No asumir esas rutas antes de implementarlas y probarlas.

La implementación concreta de identidad depende del proveedor y de la política municipal; no se creó un login ficticio ni se afirma seguridad multiusuario.

## Pruebas

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall -q src
```

Las pruebas incluyen PDFs sintéticos, OCR real, persistencia al recrear la aplicación, flujos TUPA, concurrencia, autenticación, CORS y compatibilidad del modo local. La prueba HTTP adicional del frontend arranca `tests/support_frontend_server.py` en localhost con SQLite/PDF temporales y token efímero, sin tocar producción.
