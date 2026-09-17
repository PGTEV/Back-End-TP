# Backend PMV1 HU01

API Python y FastAPI para cargar un expediente PDF, extraer texto, clasificar páginas y guardar resultados. Arquitectura hexagonal: dominio independiente, aplicación coordinadora y adaptadores de infraestructura. No incluye frontend ni validación normativa del TUPA.

## Ejecutar en esta computadora

Abre esta carpeta en VS Code. El entorno `.venv` contiene las dependencias instaladas. En la terminal PowerShell, desde esta carpeta:

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.infrastructure.main:create_app --factory --host 127.0.0.1 --port 8000
```

Abre http://127.0.0.1:8000/docs. En `POST /api/expedientes`, pulsa **Try it out**, selecciona un PDF en `archivo` y pulsa **Execute**. Copia el `id` devuelto para consultar `GET /api/expedientes/{dossier_id}`. Ctrl+C detiene el servidor. Los resultados permanecen después de reiniciar.

No es necesario activar el entorno virtual ni cambiar la política de ejecución de PowerShell. En VS Code instala la extensión oficial Python y selecciona `.venv\Scripts\python.exe` como intérprete. F5 usa la configuración incluida si está instalada la extensión Python Debugger.

## Instalación en otra computadora

Instala Python 3.12 de python.org, abre la carpeta y ejecuta:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
```

El entorno de esta computadora se creó con el Python disponible de Codex. No copies `.venv` a otro equipo; recréalo con los comandos anteriores. No necesitas claves para el OCR local.

## Base de datos

Por defecto usa SQLite en `data/expedientes.db` para la demostración local. El adaptador SQLAlchemy también admite PostgreSQL. Para usar PostgreSQL, instala el servidor, crea un usuario y una base de datos y coloca la conexión en `.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://pmv:TU_CLAVE@localhost:5432/pmv
```

Las credenciales con caracteres especiales deben codificarse para URL. Reinicia el backend tras cambiar la configuración. La tabla `expedientes` se crea al arrancar: `id` es clave primaria y `payload` guarda el agregado completo en JSON. La escritura del agregado es transaccional; los originales se almacenan fuera de la BD en `data/originales`, con nombres UUID. Cambiar de SQLite a PostgreSQL no migra registros automáticamente. El esquema JSON es una propuesta mínima para coordinar con el responsable de BD; puede reemplazar este adaptador sin cambiar dominio ni aplicación.

## Arquitectura y responsabilidades

```text
Controlador FastAPI -> Caso de uso -> Entidades, reglas y puertos
                                      ^
                          Adaptadores implementan los puertos
                          SQLAlchemy / OCR / archivos locales
```

- `src/domain/entities/`: expediente y documento, sin frameworks.
- `src/domain/valueObjects/`: evidencia de extracción por página.
- `src/domain/ports/`: contratos de lector documental, repositorio y archivos.
- `src/domain/classification.py`: reglas de clasificación y extracción de campos.
- `src/application/useCases/`: procesar y consultar expediente mediante puertos.
- `src/infrastructure/adapters/input/controllers/`: HTTP, archivos recibidos, serialización y errores.
- `src/infrastructure/adapters/output`: OCR, base de datos y almacenamiento real.
- `src/infrastructure/main.py`: raíz de composición; conecta implementaciones con casos de uso.

El controlador no ejecuta SQL ni OCR. La aplicación no importa FastAPI, SQLAlchemy ni el motor OCR. Los puertos se definen en el dominio con `Protocol`, implementados por los adaptadores mediante sus métodos públicos.

## Contrato para el frontend

`POST /api/expedientes`, `multipart/form-data`, campo **archivo**. Respuesta 201 después de terminar el procesamiento, con `id`, `nombre_archivo`, `estado`, `sha256`, `creado_en`, `error` y `documentos`. Cada documento incluye `tipo`, `paginas`, `texto`, `campos`, `confianza_ocr` y `requiere_revision`.

Ejemplo de llamada desde el frontend:

```javascript
const form = new FormData();
form.append('archivo', file);
const response = await fetch('http://127.0.0.1:8000/api/expedientes', {
  method: 'POST', body: form
});
const result = await response.json();
// No establecer Content-Type manualmente: el navegador añade el boundary.
if (!response.ok) console.error(result.detail?.mensaje ?? result.detail);
```

`GET /api/expedientes/{id}` devuelve la extracción persistida o 404. `GET /health` indica que la API responde. Los orígenes CORS permitidos están en `.env.example`.

Errores: 400 PDF inválido/corrupto/protegido o demasiadas páginas; 413 archivo mayor al límite; 422 documento ilegible; 503 fallo del procesamiento. Los errores de validación de FastAPI también pueden devolver 422 con un arreglo en `detail`.

```json
{
  "detail": {
    "codigo": "DOCUMENTO_ILEGIBLE",
    "mensaje": "Documento ilegible, por favor vuelva a cargar el archivo",
    "pagina": 2,
    "id": "UUID del expediente"
  }
}
```

## OCR, clasificación y alcance real

Corrección de clasificación: un plano requiere un título técnico reconocible y etiquetas de formato (escala, lámina o cuadro de áreas). Una mención narrativa a un plano no basta. Se admiten escalas `1/500`, `1:500` y variantes con espacios; `campos.escala` devuelve el formato normalizado `1:500`, conservando el texto original. Las memorias descriptivas siguen fuera de las categorías implementadas y se devuelven como `DESCONOCIDO` para revisión.

Hay procesamiento real, sin respuestas simuladas: PyMuPDF obtiene texto de PDFs digitales y RapidOCR ejecuta modelos PP-OCR mediante ONNX para escaneos. RapidOCR es una alternativa de ejecución de la familia PaddleOCR; no es el paquete `paddleocr` seleccionado en el documento académico. El motor está aislado y se puede sustituir al coordinar la integración de IA. Documentación: https://github.com/RapidAI/RapidOCR y https://fastapi.tiangolo.com/tutorial/request-files/.

La clasificación inicial es por frases indicativas de FUT, DNI y planos. Las categorías ambiguas se devuelven como `DESCONOCIDO`, sin inventarlas. Se extraen DNI/RUC explícitamente etiquetados y escala de planos. No se interpreta geometría de planos ni se garantiza cobertura de todos los formatos municipales. Cada página constituye una unidad clasificada; no se unen páginas contiguas porque pueden contener documentos distintos. La agrupación semántica de un documento que ocupa varias páginas y una clasificación aprendida quedan para validar con el compañero de IA y expedientes representativos.

El DPI se calcula a partir de dimensiones de imagen y tamaño de colocación en el PDF, para imágenes que cubren al menos 40% de la página. No se atribuye un DPI ficticio a PDFs vectoriales. Se rechaza una imagen principal inferior a 150 DPI, aun si contiene capa de texto. Las páginas sin texto suficiente o con baja confianza OCR también se rechazan. La confianza y las reglas son umbrales de prototipo; requieren calibración con documentos reales anonimizados. Un escaneo borroso puede producir OCR de alta confianza: no se afirma detección infalible de borrosidad.

Límites predeterminados: 20 MB y 30 páginas. El procesamiento es síncrono y puede tardar en CPU; el frontend debe mostrar espera y no reenviar automáticamente. Si falla una página, no se persisten documentos parciales como exitosos. Se conserva original y estado del fallo para trazabilidad. Si el proceso del servidor se interrumpe, un expediente puede quedar en `PROCESANDO`; esta versión no incorpora cola ni recuperación automática.

El backend incluye IA local. Una API externa independiente, si el docente la exige expresamente, todavía debe conectarse mediante el puerto `DocumentReader`; no se presenta el OCR local como servicio externo. Prototipo de desarrollo local sin autenticación: usar datos ficticios/anonimizados y mantener el servidor en 127.0.0.1. No está preparado para publicación municipal.

## Pruebas

Para generar PDFs ficticios de demostración (digital, escaneado, baja resolución y página vacía):

```powershell
.\.venv\Scripts\python.exe scripts/create_demo_pdfs.py
```

Los archivos aparecen en `data/ejemplos`. Los dos primeros deben procesarse; los dos últimos deben devolver `DOCUMENTO_ILEGIBLE`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Pruebas con PDFs sintéticos, lectura de PDF digital, OCR real sobre imagen escaneada, baja resolución, página vacía, clasificación desconocida, archivo corrupto, límites, consulta y persistencia al recrear la aplicación. Incluye prueba de dependencias para evitar imports de infraestructura/frameworks en dominio y aplicación. No equivalen a un benchmark con expedientes de la MPH. PostgreSQL requiere una instancia accesible para probarlo por separado.

Verificación realizada el 17 de septiembre de 2026: 13 pruebas aprobadas en Windows con Python 3.12. También se comprobó el servidor Uvicorn real: `/docs` disponible, PDFs digital y escaneado con respuesta 201 y categorías FUT/DNI/PLANO; baja resolución y página vacía con respuesta 422; consultas posteriores coherentes. El comprobador `scripts/check_server.py` reproduce esta verificación, crea cuatro expedientes ficticios en la base configurada y detiene su propio servidor al terminar. La biblioteca de pruebas emitió dos advertencias de deprecación de dependencias, sin fallos.
