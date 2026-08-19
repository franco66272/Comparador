# TecnoRadar — publicación gratuita en Render

## Arquitectura

- Web pública: Render Free + Gunicorn.
- Datos: `productos.json` e `historial_precios.json` en GitHub.
- Actualización: GitHub Actions cada hora, lote de 200 productos.
- La web lee los datos de GitHub Raw y los mantiene en caché durante 5 minutos.
- El servicio web de Render no escribe datos persistentes.

## Publicación

1. Usar el repositorio público `franco66272/compararadar`.
2. Subir el contenido completo de este proyecto al repositorio, respetando carpetas como `.github/workflows/`, `templates/`, `static/` y `extractores/`.
3. En Render elegir **New → Blueprint** y conectar `franco66272/compararadar`.
4. Render leerá `render.yaml`, creará el servicio gratuito y generará una URL `*.onrender.com`.
5. Esperar el primer deploy y verificar `/health`.

## Importante sobre el plan gratuito

Render Free duerme el servicio después de 15 minutos sin tráfico y su sistema de archivos es efímero. Por eso la persistencia del catálogo no depende del filesystem de Render.
