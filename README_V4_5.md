# V4.5 — Ficha de producto y verificación de precios

## Nuevas funciones

- Cada tarjeta abre una ficha interna del producto.
- La ficha intenta obtener descripción, imagen y precio desde la página oficial.
- Se conserva el enlace para abrir el sitio oficial del vendedor.
- Se crea `historial_precios.json` por producto.
- El historial alimenta un gráfico de evolución del precio.
- `verificar_precios.py` verifica un lote de productos, detecta diferencias y actualiza `productos.json` cuando encuentra un precio oficial distinto.
- `verificar_precios_continuo.py` ejecuta ciclos automáticamente.
- La verificación es incremental para evitar hacer miles de requests simultáneas.
- La portada muestra el total real de productos cargados en `productos.json` y ya no muestra “24/7”.

## Verificación continua

Desde `scraper`:

```bat
..\venv\Scripts\python.exe verificar_precios_continuo.py
```

Por defecto ejecuta un lote de 120 productos cada 15 minutos y evita volver a verificar el mismo producto antes de 12 horas. Se puede ajustar:

```bat
..\venv\Scripts\python.exe verificar_precios_continuo.py --cada-minutos 15 --lote 120 --workers 8 --horas 12
```

Esto es intencionalmente incremental: verificar los 17.000+ productos en cada ciclo sería una carga excesiva para las tiendas. Con lotes se reparte la carga durante el día y se actualiza automáticamente el catálogo cuando se detectan cambios.

## Historial

El historial incluido arranca con una observación inicial tomada del catálogo actual. No reconstruye precios anteriores porque esos datos no existen en la versión anterior del proyecto. A partir de esta versión se agregan puntos cuando cambia el precio o, como máximo, una vez cada 24 horas.
