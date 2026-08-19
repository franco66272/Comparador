# TecnoRadar V4.8

## Novedad principal
Se incorporó un menú desplegable **Categorías** en el encabezado.

Las categorías se calculan automáticamente desde el catálogo, sin modificar las claves internas ni requerir una categoría distinta para cada tienda.

### Categorías actuales
- Placas de video
- Procesadores
- Motherboards
- Memorias RAM
- Almacenamiento
- Fuentes
- Gabinetes
- Refrigeración
- Monitores
- Notebooks
- PC armadas
- Teclados
- Mouse
- Auriculares
- Micrófonos
- Webcams
- Joysticks y controles
- Impresoras
- Redes y WiFi
- Accesorios
- Otros

Cada elemento muestra la cantidad de productos y lleva directamente al catálogo filtrado. La clasificación usa el campo `categoria` si alguna fuente lo proporciona y, si no, aplica reglas universales al nombre del producto.

## Uso
No hay que reconstruir `productos.json` para probar el menú.

```bat
cd C:\Users\Garcias\comparador-precios\scraper
..\venv\Scripts\python.exe app.py
```

Abrir `http://127.0.0.1:5000`.
