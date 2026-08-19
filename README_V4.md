# Comparador Universal V4

## Qué cambia

Esta versión conserva los extractores históricos y los catálogos existentes, pero el flujo automático usa un motor universal de adquisición de catálogos.

Flujo:

Tienda -> detección -> descubrimiento de fuentes -> priorización -> extracción -> validación -> merge -> productos.json -> app.py

### Protecciones

- límite de tiempo por tienda: 150 s
- máximo de requests: 120
- máximo de páginas: 80
- máximo de fuentes recorridas: 8
- máximo de candidatos: 80
- circuit breaker
- deduplicación
- paginación explícita
- filtro de relevancia por señales de producto
- exclusión de categorías claramente ajenas a tecnología
- fallback y merge incremental
- estado de salud por tienda
- reintento de tiendas pendientes

### Fuentes priorizadas

1. APIs/feed/JSON estructurado detectado
2. JSON-LD Product
3. endpoints internos detectados
4. sitemap filtrado por relevancia
5. categorías relevantes
6. HTML de productos
7. fallback genérico

El sitemap no se trata como catálogo automáticamente: primero se filtran y priorizan sus URLs.

## Archivos principales

- `actualizar.py`: actualiza todas las tiendas y genera `productos.json`.
- `agregar_tienda.py`: incorpora una tienda nueva y genera su configuración automática.
- `agregar_lote.py`: procesa el lote y reintenta `config/tiendas_pendientes.json`.
- `extractores/auto_generico.py`: motor universal.
- `extractores/runner_auto.py`: aislamiento de cada extractor.
- `validacion/validar.py`: validación y merge incremental.
- `config/tiendas_auto.json`: registro compacto de tiendas.
- `config/salud_tiendas.json`: estado de salud de la última ejecución.
- `productos.json`: catálogo unificado consumido por la web.
- `app.py`: interfaz Flask.
- `config/tiendas_pendientes.json`: tiendas aún no incorporadas o pendientes de reintento.

## Ejecución

Desde:

`C:\Users\Garcias\comparador-precios\scraper`

Python:

`..\venv\Scripts\python.exe`

Actualizar:

`..\venv\Scripts\python.exe actualizar.py`

Web:

`..\venv\Scripts\python.exe app.py`

Luego abrir:

`http://127.0.0.1:5000/`

Estado de tiendas:

`http://127.0.0.1:5000/salud`

Instalación/actualización de dependencias:

`..\venv\Scripts\python.exe -m pip install -r requirements_universal.txt`

## Compatibilidad

Los catálogos individuales existentes no se borran. Las tiendas históricas que tienen extractores propios siguen usando sus mecanismos actuales. El motor universal se utiliza para las tiendas registradas como automáticas.

La nueva versión no requiere crear un scraper nuevo por tienda cuando el motor universal puede descubrir la fuente.
