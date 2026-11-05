# Lote de 500 expedientes académicos

El generador crea expedientes ficticios diferentes y los carga a través de las rutas HTTP del backend, usando FastAPI TestClient y una base SQLite local. No lee .env, no escribe en Supabase y deshabilita los proveedores generativos. No se crean registros directamente para simular un procesamiento que no ocurrió: cada expediente pasa por carga, extracción digital, clasificación, privacidad, persistencia, validación académica y consulta posterior.

## Reproducir

Desde el repositorio backend con sus dependencias de desarrollo instaladas:

```powershell
python -m scripts.batch_demo_records --count 500 --output data/evaluacion-500
```

La carpeta debe ser nueva o estar vacía. La ejecución no sobrescribe lotes existentes. La cantidad admitida es de 1 a 1000 expedientes; el valor predeterminado es 500. Para otros ensayos usar otra carpeta. El token del revisor del ensayo se genera en memoria, no se imprime ni se exporta.

## Composición de 500 registros

Se generan 200 casos conformes, 100 sin evidencia ficticia de pago, 100 con DNI del recibo diferente, 50 con plano sin firma ficticia y 50 con asunto ambiguo. Los casos se distribuyen entre los tres códigos TUPA del catálogo piloto. Todos los PDF muestran marcas de datos ficticios, referencia de lote e identidades generadas sin utilizar datos de ciudadanos. Cada expediente tiene ID y hash de PDF diferentes.

Los expedientes conformes pasan por el modelo de enrutamiento sintético local; los ambiguos deben ir a clasificación manual. Los casos observados o pendientes no se derivan. No se emiten firmas, registros SISGEDOC ni notificaciones.

## Archivos obtenidos

- evaluacion.sqlite contiene 500 filas en expedientes y 500 en flujos_municipales.
- originales contiene un PDF por expediente, nombrado por su ID real de persistencia.
- registros.csv permite revisar los 500 casos, IDs, hashes, resultados, páginas y latencias.
- resumen.json contiene los conteos comprobados y las condiciones de ejecución.
- expedientes_supabase.csv y flujos_municipales_supabase.csv contienen las columnas de las tablas actuales y el payload JSON exportado.
- consultas_verificacion_supabase.sql contiene consultas de solo lectura para revisar los registros ficticios después de una importación manual.

Los 500 expedientes no deben confundirse con sus documentos/páginas, con las 1000 filas físicas de ambas tablas ni con las pruebas unitarias. Una operación completa de este lote puede ejecutar varias solicitudes HTTP sobre el mismo expediente.

## Evidencia de la ejecución local entregada

Se verificaron 500 expedientes, 500 flujos y 500 PDFs con hashes distintos. Se procesaron 2498 páginas digitales. La distribución por código fue PA12115285: 200, PA121121B0: 151 y PE1027344C1: 149. Los resultados fueron 250 CONFORME, 150 OBSERVADO y 100 PENDIENTE_REVISION, siempre bajo reglas de demostración académica.

La ejecución secuencial con concurrencia 1 duró 33.323 segundos, incluyendo generación y procesamiento del lote, antes de exportar CSV y empaquetar. La mediana de carga fue 20.184 ms y el percentil 95 por rango más cercano fue 37.751 ms. La mediana del caso completo fue 42.575 ms y su percentil 95 fue 78.441 ms. El entorno fue Windows con Python 3.12.7, SQLite y transporte ASGI interno. Estos valores no representan latencia de Internet, Render o Supabase.

Se ejecutaron 500 altas, 500 validaciones, 250 evaluaciones de enrutamiento y 500 consultas, equivalentes a 1750 solicitudes ASGI sobre 500 expedientes. No se hicieron inferencias OCR de imágenes en este lote: los PDF contienen texto digital. Tampoco se llamó a Gemini/OpenAI. No constituye una evaluación de precisión con expedientes reales, un ensayo de concurrencia ni validación de reglas normativas sobre originales ciudadanos.

La verificación del código aprobó 161 pruebas backend y compileall. El lote pequeño de pruebas verifica conteos, escenarios, identidad de archivos, exportaciones, protección frente a variables de conexión externas y rechazo de sobreescritura.

## Si el docente exige Supabase

Primero seleccionar expresamente un entorno de calidad y comprobar respaldo, permisos y estructura. Importar expedientes_supabase.csv en expedientes y después flujos_municipales_supabase.csv en flujos_municipales. Los CSV contienen datos ficticios y no modifican el esquema. Revisar los conteos y algunas filas después de importar; la ejecución del generador no realiza esta importación.

Importar CSV no transfiere los PDF. Para que el backend pueda previsualizarlos, originales debe copiarse al STORAGE_DIR persistente elegido, conservando sus nombres por UUID. No se debe afirmar que los archivos se encuentran en Supabase Storage: ese adaptador no está implementado. No colocar claves de Supabase ni del proveedor en el frontend, archivos exportados o GitHub.

Para demostrar los registros en una instancia local del sistema, apuntar DATABASE_URL a la SQLite entregada y STORAGE_DIR a originales, usando una credencial de revisor propia y ACADEMIC_DEMO=true. Los IDs de registros.csv se pueden consultar desde la interfaz. No reutilizar el token temporal del generador: no se guarda ni se entrega.
