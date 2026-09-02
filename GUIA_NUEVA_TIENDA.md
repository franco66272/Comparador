# Agregar una tienda

No hay que modificar la web ni el gráfico. Creá un extractor compatible con
`extractores.runner_auto` y agregalo en `config/tiendas_auto.json`:

```json
"mi_tienda_com_ar": {
  "url": "https://www.mi-tienda.com.ar",
  "extractor": "extractores.mi_tienda_com_ar",
  "estado": "activo",
  "nombre": "Mi Tienda",
  "logo": "https://www.mi-tienda.com.ar/logo.png"
}
```

Solo `url`, `extractor` y `estado` son obligatorios. Sin `nombre` o `logo`, la
web deriva un nombre legible y el favicon del dominio. Cada producto debe
tener `nombre`, `precio`, `url` e `id_producto`; `stock` e `imagen` son
opcionales.

Al ejecutar `actualizar.py`, el sistema normaliza los datos, elimina
duplicados, conserva el catálogo previo si la extracción es parcial o falla,
actualiza categorías e historial y crea los gráficos automáticamente.
